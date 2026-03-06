`timescale 1ns / 1ps

/*
 * Module: drc_makeup_apply
 * Description: Tahap 4 DRC - Mengalikan Makeup Gain ke Smoothed Gain, 
 * lalu menerapkan Gain Final ke sinyal audio. Dilengkapi dengan logika Saturation.
 * Input:  {Smooth_Gain[31:0], Audio_Q30[31:0]}
 * Output: {Processed_Audio_Q30[31:0]}
 */

module drc_makeup_apply #(
    parameter integer DATAW_IN_PACKED    = 64, 
    parameter integer DATAW_OUT_AUDIO    = 32, 
    parameter integer C_S_AXI_ADDR_WIDTH = 10,
    parameter integer C_S_AXI_DATA_WIDTH = 32
)(
    // --- Global Signals ---
    input  wire clk,
    input  wire rst_n,

    // --- AXI-Lite Interface (Makeup Gain Control) ---
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

    // --- AXI-Stream Slave (Input dari Gain Smoothing) ---
    input  wire [DATAW_IN_PACKED-1:0] s_axis_tdata,
    input  wire s_axis_tvalid,
    output wire s_axis_tready,
    input  wire s_axis_tlast,

    // --- AXI-Stream Master (Output ke PCM Formatter) ---
    output reg  [DATAW_OUT_AUDIO-1:0] m_axis_tdata,
    output reg  m_axis_tvalid,
    input  wire m_axis_tready,
    output reg  m_axis_tlast
);

    // ============================================================
    // 1. CONSTANTS & AXI-LITE REGISTERS
    // ============================================================
    localparam signed [31:0] ONE_Q30  = 32'sd1073741824;
    localparam signed [31:0] TWO_Q30  = 32'sd2147483647; 
    localparam signed [31:0] ZERO_Q30 = 32'sd0;
    localparam signed [31:0] MIN_Q30  = -32'sd1073741824;
    localparam signed [63:0] HALF_Q30 = 64'sd536870912;

    reg signed [31:0] reg_makeup;
    reg axi_awready, axi_wready, axi_bvalid;
    reg axi_arready, axi_rvalid;
    reg [31:0] axi_rdata;

    assign s_axi_awready = axi_awready;
    assign s_axi_wready  = axi_wready;
    assign s_axi_bvalid  = axi_bvalid;
    assign s_axi_bresp   = 2'b00;
    assign s_axi_arready = axi_arready;
    assign s_axi_rvalid  = axi_rvalid;
    assign s_axi_rdata   = axi_rdata;
    assign s_axi_rresp   = 2'b00;

    // AXI-Lite Write & Read Process
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            axi_awready <= 0; axi_wready <= 0; axi_bvalid <= 0;
            axi_arready <= 0; axi_rvalid <= 0;
            reg_makeup  <= ONE_Q30; // Default Makeup Gain = 1.0
        end else begin
            axi_awready <= s_axi_awvalid && s_axi_wvalid && !axi_bvalid;
            axi_wready  <= axi_awready;
            if (axi_awready) begin
                if (s_axi_awaddr[9:2] == 8'h00) reg_makeup <= $signed(s_axi_wdata);
                axi_bvalid <= 1;
            end else if (axi_bvalid && s_axi_bready) axi_bvalid <= 0;

            axi_arready <= s_axi_arvalid && !axi_rvalid;
            if (axi_arready) begin
                axi_rvalid <= 1;
                axi_rdata  <= (s_axi_araddr[9:2] == 8'h00) ? reg_makeup : 32'd0;
            end else if (axi_rvalid && s_axi_rready) axi_rvalid <= 0;
        end
    end

    // ============================================================
    // 2. CDC & SAFETY CLAMPING
    // ============================================================
    reg signed [31:0] mk_sync1, mk_sync2, mk_clamped;
    always @(posedge clk) begin
        mk_sync1 <= reg_makeup;
        mk_sync2 <= mk_sync1;
        // Clamp Makeup Gain antara 0.0 hingga 2.0 (Q30)
        if (mk_sync2 < ZERO_Q30)      mk_clamped <= ZERO_Q30;
        else if (mk_sync2 > TWO_Q30)  mk_clamped <= TWO_Q30;
        else                          mk_clamped <= mk_sync2;
    end

    // ============================================================
    // 3. PROCESSING PIPELINE (5-STAGE)
    // ============================================================
    reg signed [31:0] st1_gain, st1_audio, st2_audio, st3_audio, st3_gain_final;
    reg st1_valid, st1_last, st2_valid, st2_last, st3_valid, st3_last, st4_valid, st4_last;

    (* use_dsp = "yes" *) reg signed [63:0] st2_g_mul_mk; // Gain x Makeup
    (* use_dsp = "yes" *) reg signed [63:0] st4_a_mul_g;  // Audio x Gain_Final
    
    reg signed [31:0] rounded_g;
    reg signed [31:0] final_audio;
    
    wire pipe_en = !m_axis_tvalid || m_axis_tready;
    assign s_axis_tready = pipe_en;

    always @(posedge clk) begin
        if (!rst_n) begin
            st1_valid <= 0; st2_valid <= 0; st3_valid <= 0; st4_valid <= 0;
            m_axis_tvalid <= 0; m_axis_tdata <= 0; m_axis_tlast <= 0;
        end else if (pipe_en) begin
            
            // STAGE 1: Input Latch
            st1_valid <= s_axis_tvalid;
            if (s_axis_tvalid) begin
                st1_gain  <= s_axis_tdata[63:32];
                st1_audio <= s_axis_tdata[31:0];
                st1_last  <= s_axis_tlast;
            end

            // STAGE 2: Makeup Gain Application (Smooth Gain * Makeup)
            st2_valid <= st1_valid;
            if (st1_valid) begin
                st2_g_mul_mk <= st1_gain * mk_clamped;
                st2_audio    <= st1_audio;
                st2_last     <= st1_last;
            end

            // STAGE 3: Final Gain Rounding & Zero Clipping
            st3_valid <= st2_valid;
            if (st2_valid) begin
                // Rounding Q60 back to Q30
                rounded_g = (st2_g_mul_mk + HALF_Q30) >>> 30;
                st3_gain_final <= (rounded_g < 0) ? ZERO_Q30 : rounded_g;
                st3_audio      <= st2_audio;
                st3_last       <= st2_last;
            end

            // STAGE 4: Apply Gain to Audio Sample (Audio * Final Gain)
            st4_valid <= st3_valid;
            if (st3_valid) begin
                st4_a_mul_g <= st3_audio * st3_gain_final;
                st4_last    <= st3_last;
            end

            // STAGE 5: Final Saturation (+1.0 / -1.0) & Output
            m_axis_tvalid <= st4_valid;
            if (st4_valid) begin
                final_audio = (st4_a_mul_g + HALF_Q30) >>> 30;
                
                // Hard Clipping to prevent digital wrapping
                if (final_audio > ONE_Q30)      m_axis_tdata <= ONE_Q30;
                else if (final_audio < MIN_Q30) m_axis_tdata <= MIN_Q30;
                else                            m_axis_tdata <= final_audio;
                
                m_axis_tlast <= st4_last;
            end
        end
    end
endmodule