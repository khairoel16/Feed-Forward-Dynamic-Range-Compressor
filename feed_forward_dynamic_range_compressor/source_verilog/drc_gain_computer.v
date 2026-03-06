`timescale 1ns / 1ps

/*
 * Module: drc_gain_computer
 * Description: Tahap 2 DRC - Menghitung faktor reduksi gain (Hard-Knee).
 * Menggunakan algoritma pembagian Newton-Raphson 22-stage pipeline.
 * Input:  {Envelope[31:0], Audio_Q30[31:0]}
 * Output: {Raw_Gain[31:0], Audio_Q30[31:0]}
 */

module drc_gain_computer #(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 5,
    parameter integer C_AXIS_TDATA_WIDTH = 64 
)(
    // --- Clock & Reset ---
    input  wire aclk,
    input  wire aresetn,

    // --- AXI-Lite Interface (Threshold & Ratio Control) ---
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
    input  wire [C_AXIS_TDATA_WIDTH-1:0] s_axis_tdata,
    input  wire s_axis_tvalid,
    output wire s_axis_tready,
    input  wire s_axis_tlast,

    output reg  [C_AXIS_TDATA_WIDTH-1:0] m_axis_tdata,
    output reg  m_axis_tvalid,
    input  wire m_axis_tready,
    output reg  m_axis_tlast
);

    // ============================================================
    // 1. PARAMETERS & CONSTANTS
    // ============================================================
    localparam integer FIXED        = 30;
    localparam signed [31:0] ONE_Q30 = 32'h40000000;
    localparam signed [63:0] TWO_Q30 = 64'sd2 << FIXED;
    localparam integer PIPE_DEPTH   = 22;

    // ============================================================
    // 2. AXI-LITE REGISTERS & DINAMIS HANDSHAKE
    // ============================================================
    reg signed [31:0] reg_threshold = 32'sh00040000;
    reg signed [31:0] reg_rinv      = 32'sh40000000;
    
    reg axi_awready, axi_wready, axi_bvalid;
    reg axi_arready, axi_rvalid;
    reg [C_S_AXI_DATA_WIDTH-1:0] axi_rdata;
    reg [C_S_AXI_ADDR_WIDTH-1:0] axi_araddr_reg;

    assign s_axi_awready = axi_awready;
    assign s_axi_wready  = axi_wready;
    assign s_axi_bvalid  = axi_bvalid;
    assign s_axi_bresp   = 2'b00;
    assign s_axi_arready = axi_arready;
    assign s_axi_rvalid  = axi_rvalid;
    assign s_axi_rdata   = axi_rdata;
    assign s_axi_rresp   = 2'b00;

    // AXI-Lite Write Process
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            axi_awready <= 0; axi_wready <= 0; axi_bvalid <= 0;
            reg_threshold <= 32'sh00040000;
            reg_rinv      <= 32'sh40000000;
        end else begin
            if (!axi_awready && s_axi_awvalid && s_axi_wvalid) begin
                axi_awready <= 1; axi_wready <= 1;
                case (s_axi_awaddr[4:2])
                    3'b000: reg_threshold <= s_axi_wdata;
                    3'b001: reg_rinv      <= s_axi_wdata;
                endcase
            end else begin
                axi_awready <= 0; axi_wready <= 0;
            end
            if (axi_awready && !axi_bvalid) axi_bvalid <= 1;
            else if (s_axi_bready)  axi_bvalid <= 0;
        end
    end

    // AXI-Lite Read Process (Read-Back)
    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            axi_arready <= 0; axi_rvalid <= 0; axi_rdata <= 0;
            axi_araddr_reg <= 0;
        end else begin
            if (!axi_arready && s_axi_arvalid) begin
                axi_arready <= 1;
                axi_araddr_reg <= s_axi_araddr;
            end else begin
                axi_arready <= 0;
            end
            
            if (axi_arready && !axi_rvalid) begin
                axi_rvalid <= 1;
                case (axi_araddr_reg[4:2])
                    3'b000: axi_rdata <= reg_threshold;
                    3'b001: axi_rdata <= reg_rinv;
                    default: axi_rdata <= 32'd0;
                endcase
            end else if (axi_rvalid && s_axi_rready) begin
                axi_rvalid <= 0;
            end
        end
    end

    // ============================================================
    // 3. CDC & MATH FUNCTIONS
    // ============================================================
    reg signed [31:0] sync_T, sync_RINV;
    always @(posedge aclk) begin
        sync_T    <= reg_threshold;
        sync_RINV <= reg_rinv;
    end

    function [5:0] lzc32(input [31:0] v);
        integer k;
        reg found;
        begin
            lzc32 = 0; found = 0;
            for (k = 31; k >= 0; k = k - 1) begin
                if (v[k] && !found) begin
                    lzc32 = 31 - k;
                    found = 1;
                end
            end
            if (!found) lzc32 = 32;
        end
    endfunction

    function signed [31:0] lut64_q30(input [5:0] idx);
        case (idx)
            6'h00: lut64_q30 = 32'h7FFFFFFF; 6'h01: lut64_q30 = 32'h7C000000; 6'h02: lut64_q30 = 32'h78000000; 6'h03: lut64_q30 = 32'h74000000;
            6'h04: lut64_q30 = 32'h70000000; 6'h05: lut64_q30 = 32'h6C000000; 6'h06: lut64_q30 = 32'h68000000; 6'h07: lut64_q30 = 32'h64000000;
            6'h08: lut64_q30 = 32'h60000000; 6'h09: lut64_q30 = 32'h5C000000; 6'h0A: lut64_q30 = 32'h58000000; 6'h0B: lut64_q30 = 32'h54000000;
            6'h0C: lut64_q30 = 32'h50000000; 6'h0D: lut64_q30 = 32'h4C000000; 6'h0E: lut64_q30 = 32'h48000000; 6'h0F: lut64_q30 = 32'h44000000;
            6'h10: lut64_q30 = 32'h42000000; 6'h11: lut64_q30 = 32'h40000000; 6'h12: lut64_q30 = 32'h3E000000; 6'h13: lut64_q30 = 32'h3C000000;
            6'h14: lut64_q30 = 32'h3A000000; 6'h15: lut64_q30 = 32'h38000000; 6'h16: lut64_q30 = 32'h36000000; 6'h17: lut64_q30 = 32'h34000000;
            6'h18: lut64_q30 = 32'h32000000; 6'h19: lut64_q30 = 32'h30000000; 6'h1A: lut64_q30 = 32'h2E000000; 6'h1B: lut64_q30 = 32'h2C000000;
            6'h1C: lut64_q30 = 32'h2A000000; 6'h1D: lut64_q30 = 32'h28000000; 6'h1E: lut64_q30 = 32'h26000000; 6'h1F: lut64_q30 = 32'h24000000;
            6'h20: lut64_q30 = 32'h22000000; 6'h21: lut64_q30 = 32'h20000000; 6'h22: lut64_q30 = 32'h1E000000; 6'h23: lut64_q30 = 32'h1C000000;
            6'h24: lut64_q30 = 32'h1A000000; 6'h25: lut64_q30 = 32'h18000000; 6'h26: lut64_q30 = 32'h16000000; 6'h27: lut64_q30 = 32'h14000000;
            6'h28: lut64_q30 = 32'h13000000; 6'h29: lut64_q30 = 32'h12000000; 6'h2A: lut64_q30 = 32'h11000000; 6'h2B: lut64_q30 = 32'h10000000;
            6'h2C: lut64_q30 = 32'h0F000000; 6'h2D: lut64_q30 = 32'h0E000000; 6'h2E: lut64_q30 = 32'h0D000000; 6'h2F: lut64_q30 = 32'h0C000000;
            6'h30: lut64_q30 = 32'h0B800000; 6'h31: lut64_q30 = 32'h0B000000; 6'h32: lut64_q30 = 32'h0A800000; 6'h33: lut64_q30 = 32'h0A000000;
            6'h34: lut64_q30 = 32'h09800000; 6'h35: lut64_q30 = 32'h09000000; 6'h36: lut64_q30 = 32'h08800000; 6'h37: lut64_q30 = 32'h08000000;
            6'h38: lut64_q30 = 32'h07800000; 6'h39: lut64_q30 = 32'h07000000; 6'h3A: lut64_q30 = 32'h06800000; 6'h3B: lut64_q30 = 32'h06000000;
            6'h3C: lut64_q30 = 32'h05800000; 6'h3D: lut64_q30 = 32'h05000000; 6'h3E: lut64_q30 = 32'h04800000; 6'h3F: lut64_q30 = 32'h04000000;
            default: lut64_q30 = 32'h40000000;
        endcase
    endfunction

    // ============================================================
    // 4. PIPELINE INFRASTRUCTURE
    // ============================================================
    reg signed [31:0] x_pipe [0:PIPE_DEPTH];
    reg v_pipe [0:PIPE_DEPTH];
    reg l_pipe [0:PIPE_DEPTH];

    // Stage registers with explicit DSP mapping
    reg signed [31:0] st0_env, st0_T, st0_RINV; reg st0_c;
    (* use_dsp = "yes" *) reg signed [63:0] st1_num; reg signed [31:0] st1_env; reg st1_c;
    reg signed [31:0] st2_env; reg signed [63:0] st2_num; reg st2_c;
    reg [5:0] st3_lz;  (* use_dsp = "yes" *) reg signed [63:0] st3_xn, st3_num; reg st3_c;
    (* use_dsp = "yes" *) reg signed [63:0] st4_xn, st4_num; reg [5:0] st4_lz; reg signed [31:0] st4_y; reg st4_c;

    // Newton-Raphson Pipeline (12 stages)
    (* use_dsp = "yes" *) reg signed [63:0] nr_x[0:12], nr_n[0:12], nr_p[0:12], nr_d[0:12], nr_y[0:12], nr_yb[0:12];
    reg [5:0] nr_lz[0:12]; reg nr_c[0:12];

    // Final Gain Stages
    reg signed [95:0] st17_inv; reg signed [63:0] st17_num; reg st17_c;
    (* use_dsp = "yes" *) reg signed [159:0] st18_prod; reg st18_c;
    reg signed [31:0] st19_g, st20_g;

    assign s_axis_tready = !m_axis_tvalid || m_axis_tready;

    // ============================================================
    // 5. MAIN PIPELINE PROCESS
    // ============================================================
    integer i, j;
    always @(posedge aclk) begin
        if (!aresetn) begin
            m_axis_tvalid <= 0;
            m_axis_tlast  <= 0;
            m_axis_tdata  <= 0;
            for (i=0; i<=PIPE_DEPTH; i=i+1) begin
                v_pipe[i] <= 0;
                l_pipe[i] <= 0;
                x_pipe[i] <= 0;
            end
        end else if (s_axis_tready) begin
            
            // --- CONTROL & DATA ALIGNMENT SHIFT ---
            v_pipe[0] <= s_axis_tvalid;
            l_pipe[0] <= s_axis_tlast;
            x_pipe[0] <= s_axis_tdata[31:0];
            for (j=1; j<=PIPE_DEPTH; j=j+1) begin
                v_pipe[j] <= v_pipe[j-1];
                l_pipe[j] <= l_pipe[j-1];
                x_pipe[j] <= x_pipe[j-1];
            end

            // --- STAGE 0: Data Capture ---
            st0_env  <= s_axis_tdata[63:32]; 
            st0_T    <= sync_T; 
            st0_RINV <= sync_RINV;
            st0_c    <= ($signed(s_axis_tdata[63:32]) > $signed(sync_T));

            // --- STAGE 1: Numerator Calculation ---
            st1_env <= st0_env; st1_c <= st0_c;
            st1_num <= $signed(st0_T) + (($signed(st0_env - st0_T) * $signed(st0_RINV)) >>> FIXED);

            // --- STAGE 2: Safety Check (No Zero) ---
            st2_env <= (st1_env == 0) ? ONE_Q30 : st1_env; 
            st2_num <= st1_num; st2_c <= st1_c;

            // --- STAGE 3: Normalization via LZC ---
            st3_lz  <= lzc32(st2_env); 
            st3_xn  <= $signed({32'sd0, st2_env}) << lzc32(st2_env);
            st3_num <= st2_num; st3_c <= st2_c;

            // --- STAGE 4: LUT Initial Seed ---
            st4_xn  <= st3_xn; st4_lz <= st3_lz; st4_num <= st3_num; st4_c <= st3_c;
            st4_y   <= lut64_q30(st3_xn[31 -: 6]);

            // --- STAGE 5: NR Loop Entry ---
            nr_x[0]  <= st4_xn; nr_n[0] <= st4_num; nr_lz[0] <= st4_lz; nr_c[0] <= st4_c; nr_yb[0] <= st4_y;

            // --- STAGES 6-16: Newton-Raphson Iterations ---
            for (j=1; j<=12; j=j+1) begin
                nr_x[j]  <= nr_x[j-1];
                nr_n[j]  <= nr_n[j-1];
                nr_lz[j] <= nr_lz[j-1];
                nr_c[j]  <= nr_c[j-1];
                
                if (j % 3 == 1)      nr_p[j] <= (nr_x[j-1] * nr_yb[j-1]) >>> FIXED;
                else                 nr_p[j] <= nr_p[j-1];

                if (j % 3 == 2)      nr_d[j] <= TWO_Q30 - nr_p[j-1];
                else                 nr_d[j] <= nr_d[j-1];

                if (j % 3 == 0)      nr_yb[j] <= (nr_yb[j-1] * nr_d[j-1]) >>> FIXED;
                else                 nr_yb[j] <= nr_yb[j-1];
            end

            // --- STAGE 17: Denormalization ---
            st17_inv <= $signed({32'sd0, nr_yb[12]}) << nr_lz[12];
            st17_num <= nr_n[12]; st17_c <= nr_c[12];

            // --- STAGE 18: Final Gain Multiplication ---
            st18_prod <= $signed(st17_num) * $signed(st17_inv); 
            st18_c    <= st17_c;

            // --- STAGE 19: Clipping & Convergent Rounding ---
            if (!st18_c) begin
                st19_g <= ONE_Q30;
            end else if (((st18_prod + (160'sd1 << (FIXED-1))) >>> FIXED) > ONE_Q30) begin
                st19_g <= ONE_Q30;
            end else begin
                st19_g <= (st18_prod + (160'sd1 << (FIXED-1))) >>> FIXED;
            end

            // --- STAGE 20: Alignment Buffer ---
            st20_g <= st19_g;

            // --- STAGE 21: Output Packaging ---
            m_axis_tvalid <= v_pipe[21];
            m_axis_tlast  <= l_pipe[21];
            m_axis_tdata  <= {st20_g, x_pipe[21]};
        end
    end
endmodule