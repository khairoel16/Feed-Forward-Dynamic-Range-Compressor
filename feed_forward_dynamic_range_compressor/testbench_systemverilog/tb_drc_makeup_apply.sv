`timescale 1ns / 1ps

/**
 * Project: Dynamic Range Compressor (DRC)
 * Module: tb_drc_makeup_apply
 * Description: Testbench untuk memverifikasi Tahap 4 DRC.
 * Fitur: Konversi otomatis nilai REAL ke Q30 untuk Makeup Gain.
 */

module tb_drc_makeup_apply;

    // ============================================================
    // 1. GLOBAL CONTROL SIGNALS
    // ============================================================
    reg  aclk    = 0;
    reg  aresetn = 0;
    always #5 aclk = ~aclk; 

    // ============================================================
    // 2. AXI-LITE SIGNALS
    // ============================================================
    reg  [9:0]  axi_awaddr;
    reg         axi_awvalid;
    wire        axi_awready;
    reg  [31:0] axi_wdata;
    reg         axi_wvalid;
    wire        axi_wready;
    wire [1:0]  axi_bresp;
    wire        axi_bvalid;
    reg         axi_bready;

    reg  [9:0]  axi_araddr;
    reg         axi_arvalid;
    wire        axi_arready;
    wire [31:0] axi_rdata;
    wire [1:0]  axi_rresp;
    wire        axi_rvalid;
    reg         axi_rready;

    // ============================================================
    // 3. AXI-STREAM SIGNALS
    // ============================================================
    reg  [63:0] s_axis_tdata;
    reg         s_axis_tvalid;
    wire        s_axis_tready;
    reg         s_axis_tlast;

    wire [31:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready;
    wire        m_axis_tlast;

    // ============================================================
    // 4. DISPLAY VARIABLES & CONSTANTS
    // ============================================================
    real Q30_F = 1073741824.0;
    reg signed [31:0] current_makeup;

    // --- INPUT PARAMETER REAL (Dapat diubah untuk pengujian) ---
    real makeup_input; // Variabel untuk menginput nilai real desimal
    integer makeup_q30;

    // ============================================================
    // 5. DEVICE UNDER TEST (DUT)
    // ============================================================
    drc_makeup_apply #(
        .DATAW_IN_PACKED(64),
        .DATAW_OUT_AUDIO(32)
    ) dut (
        .clk(aclk), .rst_n(aresetn),
        .s_axi_aclk(aclk), .s_axi_aresetn(aresetn),
        .s_axi_awaddr(axi_awaddr), .s_axi_awvalid(axi_awvalid), .s_axi_awready(axi_awready),
        .s_axi_wdata(axi_wdata), .s_axi_wvalid(axi_wvalid), .s_axi_wready(axi_wready),
        .s_axi_bresp(axi_bresp), .s_axi_bvalid(axi_bvalid), .s_axi_bready(axi_bready),
        .s_axi_araddr(axi_araddr), .s_axi_arvalid(axi_arvalid), .s_axi_arready(axi_arready),
        .s_axi_rdata(axi_rdata), .s_axi_rresp(axi_rresp), .s_axi_rvalid(axi_rvalid), .s_axi_rready(axi_rready),
        .s_axis_tdata(s_axis_tdata), .s_axis_tvalid(s_axis_tvalid), .s_axis_tready(s_axis_tready), .s_axis_tlast(s_axis_tlast),
        .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid), .m_axis_tready(m_axis_tready), .m_axis_tlast(m_axis_tlast)
    );

    // ============================================================
    // 6. SIMULATION TASKS
    // ============================================================
    
    task axi_write_makeup(input signed [31:0] value);
    begin
        @(posedge aclk); #1;
        axi_awaddr <= 10'h000; axi_awvalid <= 1;
        axi_wdata  <= value;   axi_wvalid  <= 1; axi_bready <= 1;
        wait (axi_awready && axi_wready);
        @(posedge aclk); #1;
        axi_awvalid <= 0; axi_wvalid <= 0;
        wait (axi_bvalid);
        @(posedge aclk); #1; axi_bready <= 0;
        current_makeup = value;
        repeat (5) @(posedge aclk); 
    end
    endtask

    task axi_read_makeup();
    begin
        @(posedge aclk); #1;
        axi_araddr <= 10'h000; axi_arvalid <= 1; axi_rready <= 1;
        wait (axi_arready);
        @(posedge aclk); #1;
        axi_arvalid <= 0;
        wait (axi_rvalid);
        $display("[AXI-READ] Addr: 0x%h | Data: %10d (Hex: 0x%h) (REAL: %f)", 
                 axi_araddr, axi_rdata, axi_rdata, $signed(axi_rdata)/Q30_F);
        @(posedge aclk); #1;
        axi_rready <= 0;
    end
    endtask

    task send_sample(input signed [31:0] g, input signed [31:0] x, input is_last, input integer test_num);
    begin
        s_axis_tdata  <= {g, x};
        s_axis_tvalid <= 1;
        s_axis_tlast  <= is_last;
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        #1;
        s_axis_tvalid <= 0; s_axis_tlast <= 0;
        
        wait(m_axis_tvalid);
        
        $display("\nTEST %0d:", test_num);
        $display("input gain    : %h (%f)", g, g/Q30_F);
        $display("input audio   : %h (%f)", x, x/Q30_F);
        $display("input makeup  : %h (%f)", current_makeup, current_makeup/Q30_F);
        $display("");
        $display("output        : %h (%f)", m_axis_tdata, $signed(m_axis_tdata)/Q30_F);
        $display("tlast         : %b", m_axis_tlast);
        
        @(posedge aclk);
    end
    endtask

    // ============================================================
    // 7. MAIN TEST SEQUENCE
    // ============================================================
    initial begin
        // Inisialisasi
        aresetn = 0; s_axis_tdata = 0; s_axis_tvalid = 0; s_axis_tlast = 0; m_axis_tready = 1;
        axi_awvalid = 0; axi_wvalid = 0; axi_bready = 0; axi_awaddr = 0; axi_wdata = 0;
        axi_araddr = 0; axi_arvalid = 0; axi_rready = 0;

        #100 aresetn = 1; #50;

        $display("\n--- [START] MAKEUP GAIN & SATURATION TEST ---");

        // --- STEP 1: INITIAL CONFIGURATION ---
        $display("\n--- INITIAL CONFIGURATION & VERIFICATION ---");
        makeup_input = 1.0; 
        makeup_q30   = makeup_input * Q30_F;
        axi_write_makeup(makeup_q30); 
        axi_read_makeup();

        // --- STEP 2: RUN TEST CASES ---
        
        // TEST 1: Unity Makeup
        send_sample(32'sh2000_0000, -32'sh1000_0000, 0, 1);

        // TEST 2: Double Makeup (Boost 2.0)
        makeup_input = 1.999999999; // Mendekati 2.0 (Max Q30)
        makeup_q30   = makeup_input * Q30_F;
        axi_write_makeup(makeup_q30); 
        axi_read_makeup(); 
        send_sample(32'sh2000_0000, 32'sh1000_0000, 0, 2);

        // TEST 3: Reduction Makeup (Attenuation 0.5)
        makeup_input = 0.5;
        makeup_q30   = makeup_input * Q30_F;
        axi_write_makeup(makeup_q30); 
        axi_read_makeup(); 
        send_sample(32'sh4000_0000, -32'sh2000_0000, 0, 3);

        // TEST 4: Saturation Test (Clipping dengan Makeup Max)
        makeup_input = 1.999999999;
        makeup_q30   = makeup_input * Q30_F;
        axi_write_makeup(makeup_q30); 
        axi_read_makeup(); 
        send_sample(32'sh4000_0000, 32'sh3333_3333, 1, 4);

        #300;
        $display("\n--- [FINISH] ALL TESTS COMPLETED ---\n");
        $finish;
    end

endmodule