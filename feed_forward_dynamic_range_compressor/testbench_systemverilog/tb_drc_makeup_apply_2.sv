`timescale 1ns / 1ps

/**
 * Project: Dynamic Range Compressor (DRC)
 * Module: tb_drc_makeup_apply_2
 * Description: Testbench Tahap 4 DRC - Versi Lengkap dengan AXI-Lite Write & Read.
 */

module tb_drc_makeup_apply_2;

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
    integer test_idx = 1;

    // Pipeline buffer untuk menyelaraskan input dengan output (Monitoring)
    reg [63:0] p_in[0:10];
    reg [31:0] p_mk[0:10];

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
    // 6. MONITORING LOGIC (SINKRONISASI DIPERBAIKI)
    // ============================================================
    integer j;
    always @(posedge aclk) begin
        if (s_axis_tvalid && s_axis_tready) begin
            p_in[0] <= s_axis_tdata;
            p_mk[0] <= current_makeup;
            for (j = 1; j <= 10; j = j + 1) begin
                p_in[j] <= p_in[j-1];
                p_mk[j] <= p_mk[j-1];
            end
        end
    end

    always @(posedge aclk) begin
        #2; 
        if (m_axis_tvalid && m_axis_tready) begin
            $display("%-5d | %-12f | %-12f | %-15f | 0x%-8h | %-10f", 
                     test_idx, 
                     $signed(p_in[0][63:32]) / Q30_F, 
                     $signed(p_in[0][31:0])  / Q30_F,
                     $signed(p_mk[0])        / Q30_F,
                     10'h000, 
                     $signed(m_axis_tdata)   / Q30_F);
            test_idx <= test_idx + 1;
        end
    end

    // ============================================================
    // 7. SIMULATION TASKS (WRITE & READ)
    // ============================================================
    
    // Task untuk Menulis Makeup Gain
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
    end
    endtask

    // Task untuk Membaca Kembali Makeup Gain (Menghilangkan XXXXX di axi_rdata)
    task axi_read_makeup(input [9:0] addr);
    begin
        @(posedge aclk); #1;
        axi_araddr <= addr; axi_arvalid <= 1; axi_rready <= 1;
        wait (axi_arready && axi_rvalid);
        @(posedge aclk); #1;
        // Opsional: Anda bisa cek nilainya di console jika mau
        // $display("[AXI READ] Addr 0x%h = %f", addr, $signed(axi_rdata)/Q30_F);
        axi_arvalid <= 0; axi_rready <= 0;
    end
    endtask

    // ============================================================
    // 8. MAIN SIMULATION SEQUENCE
    // ============================================================
    integer i;
    real cur_g, cur_a, cur_mk;

    initial begin
        // Reset & Init
        aresetn = 0;
        s_axis_tdata = 0; s_axis_tvalid = 0; s_axis_tlast = 0;
        m_axis_tready = 1;
        axi_awvalid = 0; axi_wvalid = 0; axi_bready = 0;
        axi_awaddr = 0; axi_wdata = 0;
        axi_araddr = 0; axi_arvalid = 0; axi_rready = 0;

        current_makeup = 32'sd1073741824; // Default 1.0
        for (i = 0; i <= 10; i = i + 1) begin
            p_in[i] = 0; p_mk[i] = 0;
        end

        #100 aresetn = 1;
        #50;

        $display("\n===============================================================================");
        $display("%-5s | %-12s | %-12s | %-15s | %-10s | %-10s", 
                 "TEST", "INPUT GAIN", "INPUT AUDIO", "MAKE-UP GAIN", "AXI-ADDR", "OUTPUT");
        $display("===============================================================================");

        for (i = 0; i < 20; i = i + 1) begin
            cur_g  = 0.015 + (i * 0.05);
            cur_a  = -0.025 - (i * 0.05);
            cur_mk = 1.00 + (i * 0.05);

            // 1. TULIS nilai ke register makeup gain
            axi_write_makeup(cur_mk * Q30_F);
            
            // 2. BACA kembali nilai dari register (Verifikasi AXI-Lite)
            axi_read_makeup(10'h000);

            // 3. KIRIM Data Audio via AXI-Stream
            @(posedge aclk); #1;
            s_axis_tdata[63:32] <= cur_g * Q30_F;
            s_axis_tdata[31:0]  <= cur_a * Q30_F;
            s_axis_tvalid       <= 1;
            s_axis_tlast        <= (i == 19);

            wait (s_axis_tready);
            @(posedge aclk); #1;
            s_axis_tvalid <= 0;
            
            #20; 
        end

        wait (test_idx > 20);

        $display("===============================================================================");
        $display("\nSIMULATION FINISHED");
        $finish;
    end

endmodule