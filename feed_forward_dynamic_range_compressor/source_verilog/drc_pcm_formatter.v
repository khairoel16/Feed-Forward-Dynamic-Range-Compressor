`timescale 1ns / 1ps

/*
 * Module: drc_pcm_formatter
 * Description: Tahap 5 (Final) DRC - Konversi resolusi bit dari 32-bit (Q30)
 * Input:  {Processed_Audio_Q30[31:0]}
 * Output: {Final_PCM_16bit[15:0]}
 */

module drc_pcm_formatter #(
    parameter integer DATAW_IN_AUDIO     = 32,
    parameter integer DATAW_OUT_PCM      = 16,
    parameter integer C_S_AXI_ADDR_WIDTH = 10,
    parameter integer C_S_AXI_DATA_WIDTH = 32
)(
    // --- Global Signals ---
    input  wire clk,
    input  wire rst_n,

    // --- AXI-Lite Interface (Standard Compliance & Debug) ---
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

    // --- AXI-Stream Interface (Data Path) ---
    input  wire [DATAW_IN_AUDIO-1:0] s_axis_tdata,
    input  wire s_axis_tvalid,
    output wire s_axis_tready,
    input  wire s_axis_tlast,

    output reg  [DATAW_OUT_PCM-1:0] m_axis_tdata,
    output reg  m_axis_tvalid,
    input  wire m_axis_tready,
    output reg  m_axis_tlast
);

    // ============================================================
    // 1. AXI-LITE LOGIC (Standard Read/Write Handshake)
    // ============================================================
    reg axi_awready, axi_wready, axi_bvalid, axi_arready, axi_rvalid;
    reg [31:0] axi_rdata_reg, reg_dummy;

    assign s_axi_awready = axi_awready;
    assign s_axi_wready  = axi_wready;
    assign s_axi_bvalid  = axi_bvalid;
    assign s_axi_bresp   = 2'b00;
    assign s_axi_arready = axi_arready;
    assign s_axi_rvalid  = axi_rvalid;
    assign s_axi_rdata   = axi_rdata_reg;
    assign s_axi_rresp   = 2'b00;

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            axi_awready <= 0; 
            axi_wready  <= 0; 
            axi_bvalid  <= 0;
            axi_arready <= 0; 
            axi_rvalid  <= 0; 
            reg_dummy   <= 0;
        end else begin
            // Write channel
            if (s_axi_awvalid && s_axi_wvalid && !axi_bvalid) begin
                axi_awready <= 1; 
                axi_wready  <= 1;
                if (s_axi_awaddr[9:2] == 8'h00)
                    reg_dummy <= s_axi_wdata;
                axi_bvalid <= 1;
            end else begin
                axi_awready <= 0; 
                axi_wready  <= 0;
                if (axi_bvalid && s_axi_bready)
                    axi_bvalid <= 0;
            end

            // Read channel
            if (s_axi_arvalid && !axi_rvalid) begin
                axi_arready   <= 1; 
                axi_rvalid    <= 1;
                axi_rdata_reg <= (s_axi_araddr[9:2] == 8'h00) ? reg_dummy : 32'd0;
            end else begin
                axi_arready <= 0;
                if (axi_rvalid && s_axi_rready)
                    axi_rvalid <= 0;
            end
        end
    end

    // ============================================================
    // 2. CONSTANTS & FLOW CONTROL LOGIC
    // ============================================================
    localparam signed [31:0] HALF_LSB = 32'sd16384;
    localparam signed [15:0] P_MAX    = 16'sd32767;
    localparam signed [15:0] P_MIN    = -16'sd32768;

    wire out_fire     = m_axis_tvalid && m_axis_tready;
    wire pipe_advance = !m_axis_tvalid || out_fire;
    assign s_axis_tready = pipe_advance;

    // ============================================================
    // 3. PROCESSING PIPELINE (3-STAGE)
    // ============================================================
    reg signed [31:0] st1_d, st2_r;
    reg st1_v, st1_l, st2_v, st2_l;

    always @(posedge clk) begin
        if (!rst_n) begin
            st1_v <= 0;
            st2_v <= 0;
            st1_l <= 0;   // FIX: reset eksplisit
            st2_l <= 0;   // FIX: reset eksplisit
            m_axis_tvalid <= 0;
            m_axis_tdata  <= 0;
            m_axis_tlast  <= 0;
        end else begin
            
            // STAGE 1: Input Latch
            if (s_axis_tvalid && s_axis_tready) begin
                st1_d <= $signed(s_axis_tdata);
                st1_l <= s_axis_tlast;
                st1_v <= 1;
            end else if (pipe_advance) begin
                st1_v <= 0;
            end

            // STAGE 2: Rounding & Shift (Q30 → Q15)
            if (st1_v && pipe_advance) begin
                st2_r <= (st1_d + HALF_LSB) >>> 15;
                st2_l <= st1_l;
                st2_v <= 1;
            end else if (pipe_advance) begin
                st2_v <= 0;
            end

            // STAGE 3: Saturation & Output Handshake
            if (st2_v && pipe_advance) begin
                m_axis_tdata  <= (st2_r > 32'sd32767)  ? P_MAX :
                                 (st2_r < -32'sd32768) ? P_MIN :
                                  st2_r[15:0];
                m_axis_tlast  <= st2_l;
                m_axis_tvalid <= 1;
            end else if (out_fire) begin
                m_axis_tvalid <= 0;
            end
        end
    end

endmodule
