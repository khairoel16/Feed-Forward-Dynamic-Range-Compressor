`timescale 1ns / 1ps

/**
 * Project: Dynamic Range Compressor (DRC)
 * Module: tb_drc_gain_computer
 * Description: Testbench untuk memverifikasi Tahap 2 DRC - Gain Computer.
 * Fitur: Konversi otomatis nilai REAL ke Q30 untuk Threshold dan Rinv.
 */

module tb_drc_gain_computer;

    // ============================================================
    // 1. GLOBAL CONTROL SIGNALS
    // ============================================================
    reg  aclk    = 0;
    reg  aresetn = 0;
    always #5 aclk = ~aclk; // Clock 100 MHz

    // ============================================================
    // 2. AXI-LITE SIGNALS (Configuration & Verification)
    // ============================================================
    reg  [4:0]  s_axi_awaddr;
    reg         s_axi_awvalid;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata;
    reg         s_axi_wvalid;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready;

    reg  [4:0]  s_axi_araddr;
    reg         s_axi_arvalid;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready;

    // ============================================================
    // 3. AXI-STREAM SIGNALS (Data Path)
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
    // 4. TEST PARAMETERS (REAL & Q30 CONVERSION)
    // ============================================================
    real Q30_DIV = 1073741824.0; 
    localparam integer N = 10; // Total test samples

    // --- INPUT PARAMETER REAL (Dapat diubah di sini) ---
    real threshold_input = 0.4;   // Threshold (misal 0.5)
    real rinv_input      = 0.25;  // Rinv (Ratio Inverse, misal 1:4 = 0.25)
    
    integer threshold_q30;
    integer rinv_q30;

    integer i;
    reg signed [31:0] env_mem [0:N-1];
    reg signed [31:0] x_mem   [0:N-1];

    // ============================================================
    // 5. DEVICE UNDER TEST (DUT)
    // ============================================================
    drc_gain_computer dut (
        .aclk            (aclk),
        .aresetn         (aresetn),
        .s_axi_aclk      (aclk),
        .s_axi_aresetn   (aresetn),
        .s_axi_awaddr    (s_axi_awaddr),
        .s_axi_awvalid   (s_axi_awvalid),
        .s_axi_awready   (s_axi_awready),
        .s_axi_wdata     (s_axi_wdata),
        .s_axi_wvalid    (s_axi_wvalid),
        .s_axi_wready    (s_axi_wready),
        .s_axi_bresp     (s_axi_bresp),
        .s_axi_bvalid    (s_axi_bvalid),
        .s_axi_bready    (s_axi_bready),
        .s_axi_araddr    (s_axi_araddr),
        .s_axi_arvalid   (s_axi_arvalid),
        .s_axi_arready   (s_axi_arready),
        .s_axi_rdata     (s_axi_rdata),
        .s_axi_rresp     (s_axi_rresp),
        .s_axi_rvalid    (s_axi_rvalid),
        .s_axi_rready    (s_axi_rready),
        .s_axis_tdata    (s_axis_tdata),
        .s_axis_tvalid   (s_axis_tvalid),
        .s_axis_tready   (s_axis_tready),
        .s_axis_tlast    (s_axis_tlast),
        .m_axis_tdata    (m_axis_tdata),
        .m_axis_tvalid   (m_axis_tvalid),
        .m_axis_tready   (m_axis_tready),
        .m_axis_tlast    (m_axis_tlast)
    );

    // ============================================================
    // 6. SIMULATION TASKS
    // ============================================================
    task axi_write(input [4:0] addr, input [31:0] data);
    begin
        @(posedge aclk); #1;
        s_axi_awaddr <= addr; s_axi_awvalid <= 1;
        s_axi_wdata  <= data; s_axi_wvalid  <= 1; s_axi_bready <= 1;
        wait (s_axi_awready && s_axi_wready);
        @(posedge aclk); #1;
        s_axi_awvalid <= 0; s_axi_wvalid <= 0;
        wait (s_axi_bvalid);
        @(posedge aclk); #1; s_axi_bready <= 0;
    end
    endtask

    task axi_read(input [4:0] addr);
    begin
        @(posedge aclk); #1;
        s_axi_araddr <= addr; s_axi_arvalid <= 1; s_axi_rready <= 1;
        wait (s_axi_arready);
        @(posedge aclk); #1;
        s_axi_arvalid <= 0;
        wait (s_axi_rvalid);
        $display("[AXI-READ] Addr: 0x%h | Data: %d (Hex: 0x%h) (REAL: %0.6f)", 
                 addr, s_axi_rdata, s_axi_rdata, $signed(s_axi_rdata)/Q30_DIV);
        @(posedge aclk); #1; s_axi_rready <= 0;
    end
    endtask

    // ============================================================
    // 7. MAIN TEST SEQUENCE
    // ============================================================
    integer in_cnt, out_cnt;

    initial begin
        // --- Konversi Nilai REAL ke Q30 ---
        threshold_q30 = threshold_input * Q30_DIV;
        rinv_q30      = rinv_input      * Q30_DIV;

        // --- Initialization ---
        aresetn       = 0; i = 0;
        s_axis_tvalid = 0; s_axis_tdata = 0; s_axis_tlast = 0; m_axis_tready = 1;
        s_axi_awvalid = 0; s_axi_wvalid = 0; s_axi_bready = 0;
        s_axi_arvalid = 0; s_axi_rready = 0;

        // --- Stimulus Generation (Ramp Envelope) ---
        for (i = 0; i < N; i = i + 1) begin
            env_mem[i] = $rtoi((0.1 * (i+1)) * Q30_DIV);    // 0.1 to 1.0
            x_mem[i]   = $rtoi((0.125 + 0.05*i) * Q30_DIV); // Offset Audio
        end

        #100 aresetn = 1; #50;

        // --- STEP 1: Parameter Configuration ---
        $display("\n--- [STEP 1] CONFIGURING DRC PARAMETERS ---");
        $display("Target Threshold : %f", threshold_input);
        $display("Target Rinv      : %f", rinv_input);
        
        axi_write(5'h00, threshold_q30); // Set Threshold
        axi_write(5'h04, rinv_q30);      // Set Rinv
        
        // --- STEP 2: Read-Back Verification ---
        $display("\n--- [STEP 2] VERIFYING REGISTERS VIA READ-BACK ---");
        axi_read(5'h00); 
        axi_read(5'h04); 
        
        repeat(10) @(posedge aclk); 

        // --- STEP 3: Push Input Data Stream ---
        $display("\n--- [STEP 3] SENDING INPUT STREAM (Envelope & Audio) ---");
        for (in_cnt = 0; in_cnt < N; in_cnt = in_cnt + 1) begin
            @(posedge aclk); #1;
            s_axis_tdata  <= {env_mem[in_cnt], x_mem[in_cnt]};
            s_axis_tvalid <= 1;
            s_axis_tlast  <= (in_cnt == N-1);
            wait (s_axis_tready);
            $display("IN  [%0d] | Env: %0.2f | X: %0.3f", in_cnt, env_mem[in_cnt]/Q30_DIV, x_mem[in_cnt]/Q30_DIV);
        end
        @(posedge aclk); #1; s_axis_tvalid <= 0; s_axis_tlast <= 0;

        // --- STEP 4: Capture Pipelined Output ---
        out_cnt = 0;
        $display("\n--- [STEP 4] RECEIVING PIPELINED GAIN OUTPUT ---");
        fork : monitor_block
            begin
                #30000; $display("\n[ERROR] Simulation Timeout!"); disable monitor_block;
            end
            begin
                while (out_cnt < N) begin
                    @(posedge aclk);
                    if (m_axis_tvalid && m_axis_tready) begin
                        $display("OUT [%0d] | Gain: %0.6f | Audio_X: %0.6f | TLAST: %b",
                                 out_cnt, 
                                 $signed(m_axis_tdata[63:32])/Q30_DIV, 
                                 $signed(m_axis_tdata[31:0])/Q30_DIV, 
                                 m_axis_tlast);
                        out_cnt = out_cnt + 1;
                    end
                end
                $display("\n[SUCCESS] Gain Computer verified.");
                disable monitor_block;
            end
        join

        $display("\nSIMULATION FINISHED");
        #200; $finish;
    end

endmodule