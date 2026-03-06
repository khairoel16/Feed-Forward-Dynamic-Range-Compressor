`timescale 1ns / 1ps

/**
 * Project: Dynamic Range Compressor (DRC)
 * Module: tb_drc_envelope_follower
 * Description: Testbench untuk memverifikasi Tahap 1 DRC.
 * Perbaikan: Sinkronisasi monitor agar INPUT AUDIO sama dengan AUDIO BYPASS.
 */

module tb_drc_envelope_follower;

    // ============================================================
    // 1. GLOBAL CONTROL SIGNALS
    // ============================================================
    reg  aclk    = 0;
    reg  aresetn = 0;
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
    reg  [15:0] s_axis_tdata;
    reg         s_axis_tvalid;
    wire        s_axis_tready;
    reg         s_axis_tlast;

    wire [63:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready;
    wire        m_axis_tlast;

    // ============================================================
    // 4. DISPLAY VARIABLES & CONSTANTS
    // ============================================================
    real Q30_DIV = 1073741824.0;
    integer sample_cnt = 0;
    integer i; 
    reg [7:0] mode = 0; 
    
    // Variabel pembantu untuk monitor
    real env_val_mon;
    real input_audio_mon;    
    real audio_bypass_mon;   

    // Register penunda untuk sinkronisasi tampilan konsol (Matching DUT Latency)
    reg signed [31:0] input_q30_delayed_1;
    reg signed [31:0] input_q30_delayed_2;

    // --- INPUT PARAMETER REAL ---
    real alpha_a_input = 0.45;   
    real alpha_r_input = 0.95;   
    integer alpha_a_q30;
    integer alpha_r_q30;

    // ============================================================
    // 5. DEVICE UNDER TEST (DUT)
    // ============================================================
    drc_envelope_follower #(
        .DATAW_IN_PCM(16),
        .DATAW_OUT_PACKED(64)
    ) dut (
        .aclk            (aclk),
        .aresetn         (aresetn),
        .s_axi_aclk      (aclk),
        .s_axi_aresetn   (aresetn),
        .s_axi_awaddr    (s_axi_awaddr),
        .s_axi_awprot    (3'b000),
        .s_axi_awvalid   (s_axi_awvalid),
        .s_axi_awready   (s_axi_awready),
        .s_axi_wdata     (s_axi_wdata),
        .s_axi_wstrb     (4'hF),
        .s_axi_wvalid    (s_axi_wvalid),
        .s_axi_wready    (s_axi_wready),
        .s_axi_bresp     (s_axi_bresp),
        .s_axi_bvalid    (s_axi_bvalid),
        .s_axi_bready    (s_axi_bready),
        .s_axi_araddr    (s_axi_araddr),
        .s_axi_arprot    (3'b000),
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
    // 6. MONITORING LOGIC (PERBAIKAN SINKRONISASI)
    // ============================================================
    
    // Blok ini menunda nilai input agar muncul bersamaan dengan output m_axis
    always @(posedge aclk) begin
        if (s_axis_tvalid && s_axis_tready) begin
            input_q30_delayed_1 <= $signed(s_axis_tdata) <<< 15;
            input_q30_delayed_2 <= input_q30_delayed_1;
        end
    end

    always @(posedge aclk) begin
        if (m_axis_tvalid && m_axis_tready) begin
            // 1. Ambil Envelope (Bit 63:32)
            env_val_mon      = $signed(m_axis_tdata[63:32]) / Q30_DIV;
            
            // 2. Ambil Audio Bypass (Bit 31:0)
            audio_bypass_mon = $signed(m_axis_tdata[31:0])  / Q30_DIV;
            
            // 3. Ambil Input yang sudah ditunda agar sinkron (Latency match)
            input_audio_mon  = $signed(input_q30_delayed_2) / Q30_DIV;

            if (mode == 1)
                $display("ATTACK  | Sample %2d | INPUT AUDIO=%f | ENV=%.6f | AUDIO BYPASS=%f", 
                         sample_cnt, input_audio_mon, env_val_mon, audio_bypass_mon);
            else if (mode == 2)
                $display("RELEASE | Sample %2d | INPUT AUDIO=%f | ENV=%.6f | AUDIO BYPASS=%f", 
                         sample_cnt, input_audio_mon, env_val_mon, audio_bypass_mon);
            
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
                 addr, s_axi_rdata, s_axi_rdata, $signed(s_axi_rdata)/Q30_DIV);
        @(posedge aclk); #1;
        s_axi_rready <= 0;
    end
    endtask

    task axis_send(input signed [15:0] sample, input last);
    begin
        s_axis_tdata  <= sample;
        s_axis_tvalid <= 1;
        s_axis_tlast  <= last;
        @(posedge aclk);
        while (!s_axis_tready) @(posedge aclk);
        #1;
        s_axis_tvalid <= 0; s_axis_tlast <= 0;
    end
    endtask

    // ============================================================
    // 8. MAIN SIMULATION SEQUENCE
    // ============================================================
    initial begin
        alpha_a_q30 = alpha_a_input * Q30_DIV;
        alpha_r_q30 = alpha_r_input * Q30_DIV;

        aresetn = 0; sample_cnt = 0; mode = 0; i = 0;
        input_q30_delayed_1 = 0; input_q30_delayed_2 = 0;
        s_axis_tvalid = 0; s_axis_tdata = 0; s_axis_tlast = 0; m_axis_tready = 1;
        s_axi_awaddr = 0; s_axi_awvalid = 0; s_axi_wdata = 0; s_axi_wvalid = 0; s_axi_bready = 0;
        s_axi_araddr = 0; s_axi_arvalid = 0; s_axi_rready = 0;

        #100 aresetn = 1; #50;

        $display("\n--- [STEP 1] PROGRAMMING ALPHA COEFFICIENTS ---");
        axi_write(10'h000, alpha_a_q30); 
        axi_write(10'h004, alpha_r_q30); 

        $display("\n--- VERIFYING REGISTERS VIA READ-BACK ---");
        axi_read(10'h000); 
        axi_read(10'h004); 
        repeat(10) @(posedge aclk);

        $display("\n--- [STEP 2] SIMULATING ATTACK (Audio Jump to -16384) ---");
        sample_cnt = 0; mode = 1;
        for (i = 0; i < 20; i = i + 1) begin
            axis_send(-16'sd16384, (i == 19));
        end
        wait(sample_cnt == 20);
        repeat(5) @(posedge aclk);

        $display("\n--- [STEP 3] SIMULATING RELEASE (Audio to 0) ---");
        sample_cnt = 0; mode = 2;
        for (i = 0; i < 40; i = i + 1) begin
            axis_send(16'sd0, (i == 39));
        end
        wait(sample_cnt == 40);

        #200;
        $display("\nSIMULATION FINISHED");
        $finish;
    end

endmodule