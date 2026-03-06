`timescale 1ns / 1ps

/*
 * Module: drc_gain_smoothing
 * Description: Tahap 3 DRC - Low Pass Filter (EMA) untuk menghaluskan transisi gain.
 * Mencegah distorsi klik (zipper noise) pada audio.
 * Input:  {Raw_Gain[31:0], Audio_Q30[31:0]}
 * Output: {Smooth_Gain[31:0], Audio_Q30[31:0]}
 */

module drc_gain_smoothing #(
    parameter integer DATAW_IO_PACKED    = 64, // {Gain, Audio}
    parameter integer C_S_AXI_ADDR_WIDTH = 10,
    parameter integer C_S_AXI_DATA_WIDTH = 32
)(
    // --- Global Signals ---
    input  wire clk,
    input  wire rst_n,

    // --- AXI-Lite Interface (Smoothing Alpha Coefficients) ---
    input  wire s_axi_aclk,
    input  wire s_axi_aresetn,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input  wire s_axi_awvalid,
    output wire s_axi_awready,
    input  wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
    input  wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output wire s_axi_bvalid,
    input  wire s_axi_bready,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input  wire s_axi_arvalid,
    output wire s_axi_arready,
    output wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output wire s_axi_rvalid,
    input  wire s_axi_rready,

    // --- AXI-Stream Slave (Input dari Gain Computer) ---
    input  wire [DATAW_IO_PACKED-1:0] s_axis_tdata,
    input  wire s_axis_tvalid,
    output wire s_axis_tready,
    input  wire s_axis_tlast,

    // --- AXI-Stream Master (Output ke Makeup Gain) ---
    output reg  [DATAW_IO_PACKED-1:0] m_axis_tdata,
    output reg  m_axis_tvalid,
    input  wire m_axis_tready,
    output reg  m_axis_tlast
);

    // ============================================================
    // 1. AXI-LITE REGISTERS & DINAMIS HANDSHAKE
    // ============================================================
    reg signed [31:0] reg_alphaA = 32'sd858993459;  // Default 0.8 Q30
    reg signed [31:0] reg_alphaR = 32'sd1020054733; // Default 0.95 Q30
    
    reg axi_awready, axi_wready, axi_bvalid;
    reg axi_arready, axi_rvalid;
    reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata;
    reg [C_S_AXI_ADDR_WIDTH-1:0] axi_araddr_reg;

    assign s_axi_awready = axi_awready;
    assign s_axi_wready  = axi_wready;
    assign s_axi_bvalid  = axi_bvalid;
    assign s_axi_bresp   = 2'b00; // Jalur respon OKAY
    assign s_axi_arready = axi_arready;
    assign s_axi_rvalid  = axi_rvalid;
    assign s_axi_rdata   = axi_rdata;
    assign s_axi_rresp   = 2'b00; // Jalur respon OKAY

    // AXI-Lite Write Process (Handshake Dinamis)
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            axi_awready <= 0; axi_wready <= 0; axi_bvalid <= 0;
            reg_alphaA <= 32'sd858993459;
            reg_alphaR <= 32'sd1020054733;
        end else begin
            // Menerima awvalid dan wvalid secara simultan
            if (!axi_awready && s_axi_awvalid && s_axi_wvalid) begin
                axi_awready <= 1; axi_wready <= 1;
                case (s_axi_awaddr[4:2])
                    3'b000: reg_alphaA <= s_axi_wdata;
                    3'b001: reg_alphaR <= s_axi_wdata;
                endcase
            end else begin
                axi_awready <= 0; axi_wready <= 0;
            end
            
            if (axi_awready && !axi_bvalid) axi_bvalid <= 1;
            else if (s_axi_bready)  axi_bvalid <= 0;
        end
    end

    // AXI-Lite Read Process (Jalur Data Baca Stabil)
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            axi_arready <= 0; axi_rvalid <= 0; axi_rdata <= 0;
            axi_araddr_reg <= 0;
        end else begin
            if (!axi_arready && s_axi_arvalid) begin
                axi_arready <= 1;
                axi_araddr_reg <= s_axi_araddr; // Latch alamat baca
            end else begin
                axi_arready <= 0;
            end
            
            if (axi_arready && !axi_rvalid) begin
                axi_rvalid <= 1;
                case (axi_araddr_reg[4:2])
                    3'b000: axi_rdata <= reg_alphaA;
                    3'b001: axi_rdata <= reg_alphaR;
                    default: axi_rdata <= 32'hDEADBEEF; // Debugging
                endcase
            end else if (axi_rvalid && s_axi_rready) begin
                axi_rvalid <= 0;
            end
        end
    end

    // ============================================================
    // 2. CDC (2-FF Synchronizer)
    // ============================================================
    reg signed [31:0] sync_alphaA_ff1, sync_alphaA_ff2;
    reg signed [31:0] sync_alphaR_ff1, sync_alphaR_ff2;

    always @(posedge clk) begin
        sync_alphaA_ff1 <= reg_alphaA;
        sync_alphaA_ff2 <= sync_alphaA_ff1;
        sync_alphaR_ff1 <= reg_alphaR;
        sync_alphaR_ff2 <= sync_alphaR_ff1;
    end

    localparam signed [31:0] ONE_Q30  = 32'sd1073741824;
    localparam signed [63:0] HALF_Q30 = 64'sd536870912;
    wire signed [31:0] alphaA_val     = sync_alphaA_ff2;
    wire signed [31:0] alphaR_val     = sync_alphaR_ff2;
    wire signed [31:0] one_m_alphaA   = ONE_Q30 - alphaA_val;
    wire signed [31:0] one_m_alphaR   = ONE_Q30 - alphaR_val;

    // ============================================================
    // 3. INTERNAL SIGNAL PROCESSING (EMA Feedback Loop)
    // ============================================================
    wire pipe_ready = !m_axis_tvalid || m_axis_tready;
    assign s_axis_tready = pipe_ready;

    reg  signed [31:0] g_smooth_curr_reg;
    wire signed [31:0] g_target_in = s_axis_tdata[63:32];
    
    // Logika deteksi Attack/Release untuk Gain
    wire use_attack = (g_target_in < g_smooth_curr_reg); 
    wire signed [31:0] curr_alpha        = use_attack ? alphaA_val : alphaR_val;
    wire signed [31:0] curr_one_m_alpha  = use_attack ? one_m_alphaA : one_m_alphaR;

    (* use_dsp = "yes" *) wire signed [63:0] mul_feedback = curr_alpha * g_smooth_curr_reg;
    (* use_dsp = "yes" *) wire signed [63:0] mul_input    = curr_one_m_alpha * g_target_in;

    wire signed [63:0] sum_full    = mul_feedback + mul_input;
    wire signed [31:0] g_smooth_next = (sum_full + HALF_Q30) >>> 30;

    // ============================================================
    // 4. PIPELINE & SYNCHRONIZATION (2-STAGE)
    // ============================================================
    reg signed [31:0] pipe_x_st1, pipe_x_st2;
    reg pipe_valid_st1, pipe_valid_st2;
    reg pipe_tlast_st1, pipe_tlast_st2;

    always @(posedge clk) begin
        if (!rst_n) begin
            g_smooth_curr_reg <= ONE_Q30; // Unity Gain (1.0) on reset
            pipe_valid_st1    <= 0; pipe_valid_st2 <= 0;
            pipe_tlast_st1    <= 0; pipe_tlast_st2 <= 0;
            pipe_x_st1        <= 0; pipe_x_st2     <= 0;
        end else if (pipe_ready) begin
            // Feedback loop gain smoothing
            if (s_axis_tvalid) begin
                g_smooth_curr_reg <= g_smooth_next;
            end

            // Sinkronisasi data audio dengan gain yang diproses
            pipe_valid_st1 <= s_axis_tvalid;
            pipe_tlast_st1 <= s_axis_tlast;
            pipe_x_st1     <= s_axis_tdata[31:0];

            pipe_valid_st2 <= pipe_valid_st1;
            pipe_tlast_st2 <= pipe_tlast_st1;
            pipe_x_st2     <= pipe_x_st1;
        end
    end

    // ============================================================
    // 5. FINAL OUTPUT STAGE
    // ============================================================
    wire fire_out = pipe_valid_st2 && pipe_ready;

    always @(posedge clk) begin
        if (!rst_n) begin
            m_axis_tvalid <= 0;
            m_axis_tdata  <= 0;
            m_axis_tlast  <= 0;
        end else begin
            if (m_axis_tvalid && m_axis_tready)
                m_axis_tvalid <= 0;

            if (fire_out) begin
                m_axis_tvalid <= 1;
                m_axis_tdata  <= {g_smooth_curr_reg, pipe_x_st2};
                m_axis_tlast  <= pipe_tlast_st2;
            end
        end
    end

endmodule