`timescale 1ns / 1ps

/**
 * Project: Dynamic Range Compressor (DRC)
 * Module: tb_drc_gain_smoothing
 * Description: Testbench Tahap 3 DRC - Gain Smoothing.
 * PERBAIKAN: Sinkronisasi presisi Latency agar INPUT = BYPASS di konsol.
 */

module tb_drc_gain_smoothing;

    // ============================================================
    // 1. GLOBAL CONTROL SIGNALS
    // ============================================================
    reg  aclk  = 0;
    reg  rst_n = 0;
    always #5 aclk = ~aclk; // Clock 100 MHz

    // ============================================================
    // 2. AXI-LITE SIGNALS
    // ============================================================
    reg  [9:0]  s_axi_awaddr;
    reg         s_axi_awvalid;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata;
    reg         s_axi_wvalid;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready;

    reg  [9:0]  s_axi_araddr;
    reg         s_axi_arvalid;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready;

    // ============================================================
    // 3. AXI-STREAM SIGNALS
    // ============================================================
    reg  [63:0] s_axis_tdata;
    reg         s_axis_tvalid;
    wire        s_axis_tready;
    reg         s_axis_tlast;

    wire [63:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready;
    wire        m_axis_tlast;

    // ============================================================
    // 4. TEST CONSTANTS & MONITOR VARIABLES
    // ============================================================
    localparam signed [31:0] Q30_1_0 = 32'sd1073741824;
    localparam signed [31:0] Q30_0_2 = 32'sd214748365;
    real Q30_F = 1073741824.0;

    integer sample_cnt = 0; 
    reg [7:0] mode = 0; 

    // Register Penunda - Disesuaikan untuk sinkronisasi konsol
    reg [63:0] pipe_in_st1, pipe_in_st2, pipe_in_st3;

    // --- PARAMETER SMOOTHING ---
    real alpha_a_input = 0.85;   
    real alpha_r_input = 0.95;  
    integer alpha_a_q30;
    integer alpha_r_q30;

    // ============================================================
    // 5. DEVICE UNDER TEST (DUT)
    // ============================================================
    drc_gain_smoothing #(
        .DATAW_IO_PACKED(64)
    ) dut (
        .clk            (aclk),
        .rst_n          (rst_n),
        .s_axi_aclk      (aclk),
        .s_axi_aresetn  (rst_n),
        .s_axi_awaddr   (s_axi_awaddr),
        .s_axi_awvalid  (s_axi_awvalid),
        .s_axi_awready  (s_axi_awready),
        .s_axi_wdata    (s_axi_wdata),
        .s_axi_wvalid   (s_axi_wvalid),
        .s_axi_wready    (s_axi_wready),
        .s_axi_bresp    (s_axi_bresp),
        .s_axi_bvalid   (s_axi_bvalid),
        .s_axi_bready   (s_axi_bready),
        .s_axi_araddr   (s_axi_araddr),
        .s_axi_arvalid  (s_axi_arvalid),
        .s_axi_arready  (s_axi_arready),
        .s_axi_rdata    (s_axi_rdata),
        .s_axi_rresp    (s_axi_rresp),
        .s_axi_rvalid   (s_axi_rvalid),
        .s_axi_rready   (s_axi_rready),
        .s_axis_tdata   (s_axis_tdata),
        .s_axis_tvalid  (s_axis_tvalid),
        .s_axis_tready  (s_axis_tready),
        .s_axis_tlast   (s_axis_tlast),
        .m_axis_tdata   (m_axis_tdata),
        .m_axis_tvalid  (m_axis_tvalid),
        .m_axis_tready  (m_axis_tready),
        .m_axis_tlast   (m_axis_tlast)
    );

    // ============================================================
    // 6. MONITOR LOGIC (Sinkronisasi Presisi)
    // ============================================================
    
    // Kita menambah 1 stage lagi (st3) untuk mengimbangi 
    // delta sampling pada saat posedge clock di simulator
    always @(posedge aclk) begin
        if (s_axis_tvalid && s_axis_tready) begin
            pipe_in_st1 <= s_axis_tdata;
        end
        pipe_in_st2 <= pipe_in_st1;
        pipe_in_st3 <= pipe_in_st2;
    end

    always @(posedge aclk) begin
        // Menunggu sebentar setelah posedge agar sinyal stabil (Delta delay)
        #1; 
        if (m_axis_tvalid && m_axis_tready) begin
            if (mode != 0) begin
                $display("%s | Sample %2d | GAIN_IN=%.2f | AUDIO INPUT=%f | G_OUT=%.6f | AUDIO BYPASS=%f", 
                         (mode == 1 ? "ATTACK " : "RELEASE"),
                         sample_cnt, 
                         $signed(pipe_in_st3[63:32])/Q30_F, 
                         $signed(pipe_in_st3[31:0])/Q30_F,
                         $signed(m_axis_tdata[63:32])/Q30_F,
                         $signed(m_axis_tdata[31:0])/Q30_F);
            end
            sample_cnt <= sample_cnt + 1;
        end
    end

    // ============================================================
    // 7. SIMULATION TASKS
    // ============================================================
    task axi_write(input [9:0] addr, input [31:0] data);
    begin
        @(posedge aclk); #1;
        s_axi_awaddr <= addr; s_axi_awvalid <= 1;
        s_axi_wdata <= data; s_axi_wvalid <= 1; s_axi_bready <= 1;
        wait (s_axi_awready && s_axi_wready);
        @(posedge aclk); #1;
        s_axi_awvalid <= 0; s_axi_wvalid <= 0;
        wait (s_axi_bvalid);
        @(posedge aclk); #1; s_axi_bready <= 0;
    end
    endtask

    task axi_read(input [9:0] addr);
    begin
        @(posedge aclk); #1;
        s_axi_araddr <= addr; s_axi_arvalid <= 1; s_axi_rready <= 1;
        wait (s_axi_arready);
        @(posedge aclk); #1;
        s_axi_arvalid <= 0;
        wait (s_axi_rvalid);
        $display("[AXI-READ] Addr: 0x%h | Data: %10d (Hex: 0x%h) (REAL: %f)", 
                 addr, s_axi_rdata, s_axi_rdata, $signed(s_axi_rdata)/Q30_F);
        @(posedge aclk); #1;
        s_axi_rready <= 0;
    end
    endtask

    // ============================================================
    // 8. MAIN SIMULATION SEQUENCE
    // ============================================================
    integer i;
    reg signed [31:0] audio_counter;

    initial begin
        // Reset state
        alpha_a_q30 = alpha_a_input * Q30_F;
        alpha_r_q30 = alpha_r_input * Q30_F;
        rst_n = 0; sample_cnt = 0; mode = 0; audio_counter = 0;
        pipe_in_st1 = 0; pipe_in_st2 = 0; pipe_in_st3 = 0;
        s_axis_tvalid = 0; s_axis_tdata = 0; s_axis_tlast = 0; m_axis_tready = 1;
        s_axi_awaddr = 0; s_axi_awvalid = 0; s_axi_wdata = 0; s_axi_wvalid = 0; s_axi_bready = 0;
        s_axi_araddr = 0; s_axi_arvalid = 0; s_axi_rready = 0;

        #100 rst_n = 1; #50;

        $display("\n--- [STEP 1] CONFIGURING SMOOTHING ALPHA ---");
        axi_write(10'h000, alpha_a_q30); 
        axi_write(10'h004, alpha_r_q30); 

        $display("\n--- VERIFYING REGISTERS VIA READ-BACK ---");
        axi_read(10'h000); 
        axi_read(10'h004); 
        repeat(10) @(posedge aclk); // Memberi waktu buffer konsol

        // --- STEP 2: ATTACK ---
        $display("\n--- [STEP 2] SIMULATING ATTACK (Gain 1.0 -> 0.2) ---");
        sample_cnt = 0; mode = 1;
        for (i = 0; i < 30; i = i + 1) begin
            @(posedge aclk); #1;
            audio_counter = i * 5368709; // Increment 0.005
            s_axis_tdata  <= {Q30_0_2, audio_counter};
            s_axis_tvalid <= 1;
            s_axis_tlast  <= (i == 29);
            wait(s_axis_tready);
        end
        @(posedge aclk); #1; s_axis_tvalid = 0;
        wait(sample_cnt >= 30);
        #100;

        // --- STEP 3: RELEASE ---
        $display("\n--- [STEP 3] SIMULATING RELEASE (Gain 0.2 -> 1.0) ---");
        sample_cnt = 0; mode = 2;
        for (i = 0; i < 60; i = i + 1) begin
            @(posedge aclk); #1;
            audio_counter = (i + 30) * 5368709;
            s_axis_tdata  <= {Q30_1_0, audio_counter};
            s_axis_tvalid <= 1;
            s_axis_tlast  <= (i == 59);
            wait(s_axis_tready);
        end
        @(posedge aclk); #1; s_axis_tvalid = 0;
        wait(sample_cnt >= 60);

        #100; $display("\nSIMULATION FINISHED"); $finish;
    end

endmodule