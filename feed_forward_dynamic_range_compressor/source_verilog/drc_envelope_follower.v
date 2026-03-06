`timescale 1ns / 1ps

/*
 * Module: drc_envelope_follower
 * Description: Tahap 1 DRC - Deteksi Absolute, Ekspansi Bit ke Q30, 
 * dan One-Pole Envelope Filter (Attack/Release).
 * Perbaikan: Mengikuti standar interface AXI-Lite Tahap 3 (Fix High-Z & Unknown).
 * Output: {Envelope[31:0], Audio_Q30[31:0]}
 */

module drc_envelope_follower #(
    parameter integer DATAW_IN_PCM       = 16,
    parameter integer DATAW_OUT_PACKED   = 64, // {Envelope, Audio}
    parameter integer C_S_AXI_ADDR_WIDTH = 10,
    parameter integer C_S_AXI_DATA_WIDTH = 32
)(
    // --- Clock & Reset ---
    input  wire aclk,
    input  wire aresetn,

    // --- AXI-Lite Interface (Parameter Control) ---
    input  wire s_axi_aclk,
    input  wire s_axi_aresetn,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input  wire [2:0] s_axi_awprot,
    input  wire s_axi_awvalid,
    output wire s_axi_awready,
    input  wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_wdata,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0] s_axi_wstrb,
    input  wire s_axi_wvalid,
    output wire s_axi_wready,
    output wire [1:0] s_axi_bresp,
    output wire s_axi_bvalid,
    input  wire s_axi_bready,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input  wire [2:0] s_axi_arprot,
    input  wire s_axi_arvalid,
    output wire s_axi_arready,
    output wire [C_S_AXI_DATA_WIDTH-1:0] s_axi_rdata,
    output wire [1:0] s_axi_rresp,
    output wire s_axi_rvalid,
    input  wire s_axi_rready,

    // --- AXI-Stream Slave (Input PCM 16-bit) ---
    input  wire [DATAW_IN_PCM-1:0] s_axis_tdata,
    input  wire s_axis_tvalid,
    output wire s_axis_tready,
    input  wire s_axis_tlast,

    // --- AXI-Stream Master (Output Packed 64-bit) ---
    output reg  [DATAW_OUT_PACKED-1:0] m_axis_tdata,
    output reg  m_axis_tvalid,
    input  wire m_axis_tready,
    output reg  m_axis_tlast
);

    // ============================================================
    // 1. AXI-LITE LOGIC (Standar Perbaikan Tahap 3)
    // ============================================================
    reg axi_awready, axi_wready, axi_bvalid;
    reg axi_arready, axi_rvalid;
    reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata;
    reg [C_S_AXI_ADDR_WIDTH-1:0] axi_araddr_reg;
    reg signed [31:0] reg_alphaA, reg_alphaR;

    // Fix High-Z & Unknown melalui assignment eksplisit
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
            reg_alphaA <= 0; reg_alphaR <= 0;
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
            else if (s_axi_bready) axi_bvalid <= 0;
        end
    end

    // AXI-Lite Read Process (Jalur Data Baca Stabil/Registered)
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            axi_arready <= 0; axi_rvalid <= 0; axi_rdata <= 0;
            axi_araddr_reg <= 0;
        end else begin
            if (!axi_arready && s_axi_arvalid) begin
                axi_arready    <= 1;
                axi_araddr_reg <= s_axi_araddr; // Latch alamat baca
            end else begin
                axi_arready <= 0;
            end
            
            if (axi_arready && !axi_rvalid) begin
                axi_rvalid <= 1;
                case (axi_araddr_reg[4:2])
                    3'b000: axi_rdata <= reg_alphaA;
                    3'b001: axi_rdata <= reg_alphaR;
                    default: axi_rdata <= 32'hDEADBEEF;
                endcase
            end else if (axi_rvalid && s_axi_rready) begin
                axi_rvalid <= 0;
            end
        end
    end

    // ============================================================
    // 2. CDC (Clock Domain Crossing)
    // ============================================================
    reg signed [31:0] sync_alphaA_ff1, sync_alphaA_ff2;
    reg signed [31:0] sync_alphaR_ff1, sync_alphaR_ff2;

    always @(posedge aclk) begin
        sync_alphaA_ff1 <= reg_alphaA;
        sync_alphaA_ff2 <= sync_alphaA_ff1;
        sync_alphaR_ff1 <= reg_alphaR;
        sync_alphaR_ff2 <= sync_alphaR_ff1;
    end

    wire signed [31:0] alphaA = sync_alphaA_ff2;
    wire signed [31:0] alphaR = sync_alphaR_ff2;
    localparam signed [31:0] ONE_Q30  = 32'sd1073741824;
    localparam signed [63:0] HALF_Q30 = 64'sd536870912; 
    wire signed [31:0] one_m_alphaA = ONE_Q30 - alphaA;
    wire signed [31:0] one_m_alphaR = ONE_Q30 - alphaR;

    // ============================================================
    // 3. SIGNAL CONDITIONING (Absolut & Expansion) - Logika Asli
    // ============================================================
    wire pipe_ready = !m_axis_tvalid || m_axis_tready;
    assign s_axis_tready = pipe_ready;

    // Convert 16-bit PCM to Q1.30 format
    wire signed [31:0] x_q30 = $signed(s_axis_tdata) <<< 15;
    wire signed [31:0] abs_x = x_q30[31] ? -x_q30 : x_q30;

    // ============================================================
    // 4. CORE ENVELOPE CALCULATION (Feedback Loop) - Logika Asli
    // ============================================================
    reg  signed [31:0] env_curr_reg;
    wire use_attack = (abs_x > env_curr_reg);
    wire signed [31:0] cur_alpha        = use_attack ? alphaA : alphaR;
    wire signed [31:0] cur_one_m_alpha  = use_attack ? one_m_alphaA : one_m_alphaR;

    (* use_dsp = "yes" *) wire signed [63:0] mul_feedback = cur_alpha * env_curr_reg;
    (* use_dsp = "yes" *) wire signed [63:0] mul_input    = cur_one_m_alpha * abs_x;
    
    wire signed [63:0] sum_full = mul_feedback + mul_input;
    wire signed [31:0] env_next = (sum_full + HALF_Q30) >>> 30;

    // ============================================================
    // 5. PIPELINE & SYNCHRONIZATION
    // ============================================================
    reg signed [31:0] pipe_x_st1, pipe_x_st2; 
    reg pipe_valid_st1, pipe_valid_st2;
    reg pipe_tlast_st1, pipe_tlast_st2;

    always @(posedge aclk) begin
        if (!aresetn) begin
            env_curr_reg   <= 0; // Reset State ke 0 sesuai persyaratan
            pipe_valid_st1 <= 0; pipe_valid_st2 <= 0;
            pipe_tlast_st1 <= 0; pipe_tlast_st2 <= 0;
            pipe_x_st1     <= 0; pipe_x_st2     <= 0;
        end else if (pipe_ready) begin
            // 1-cycle Instant Feedback Loop
            if (s_axis_tvalid) begin
                env_curr_reg <= env_next;
            end

            // 2-Stage Pipeline for Output Alignment
            pipe_valid_st1 <= s_axis_tvalid;
            pipe_tlast_st1 <= s_axis_tlast;
            pipe_x_st1     <= x_q30;

            pipe_valid_st2 <= pipe_valid_st1;
            pipe_tlast_st2 <= pipe_tlast_st1;
            pipe_x_st2     <= pipe_x_st1;
        end
    end

    // ============================================================
    // 6. FINAL OUTPUT STAGE
    // ============================================================
    wire fire_out = pipe_valid_st2 && pipe_ready;

    always @(posedge aclk) begin
        if (!aresetn) begin
            m_axis_tvalid <= 0;
            m_axis_tdata  <= 0;
            m_axis_tlast  <= 0;
        end else begin
            if (m_axis_tvalid && m_axis_tready)
                m_axis_tvalid <= 0;

            if (fire_out) begin
                m_axis_tvalid <= 1;
                // Output Packed: {Envelope[31:0], Original_Audio_Q30[31:0]}
                m_axis_tdata  <= {env_curr_reg, pipe_x_st2}; 
                m_axis_tlast  <= pipe_tlast_st2;
            end
        end
    end

endmodule