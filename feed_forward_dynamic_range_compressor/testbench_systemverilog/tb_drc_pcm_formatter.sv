`timescale 1ns / 1ps
/**
 * Project : Dynamic Range Compressor (DRC)
 * Module  : tb_drc_pcm_formatter
 * Fix     : FIFO init + TLAST benar + sinkron AXI
 */

module tb_drc_pcm_formatter;

    // ============================================================
    // CLOCK & RESET
    // ============================================================
    reg aclk = 0;
    reg aresetn = 0;
    always #5 aclk = ~aclk;   // 100 MHz

    // ============================================================
    // AXI STREAM
    // ============================================================
    reg  [31:0] s_axis_tdata;
    reg         s_axis_tvalid;
    wire        s_axis_tready;
    reg         s_axis_tlast;

    wire [15:0] m_axis_tdata;
    wire        m_axis_tvalid;
    reg         m_axis_tready;
    wire        m_axis_tlast;

    // ============================================================
    // TEST PARAMETER
    // ============================================================
    real Q30_F = 1073741824.0;
    real PCM_F = 32768.0;

    integer sent_samples;
    integer recv_samples;
    integer TOTAL_SAMPLES = 47;   // 0.1 → 1.25 step 0.025

    real test_val;

    // ============================================================
    // INPUT FIFO (MONITORING ONLY)
    // ============================================================
    reg signed [31:0] input_fifo [0:255];
    integer wr_ptr;
    integer rd_ptr;
    integer i;

    // ============================================================
    // DUT
    // ============================================================
    drc_pcm_formatter dut (
        .clk           (aclk),
        .rst_n         (aresetn),

        .s_axis_tdata  (s_axis_tdata),
        .s_axis_tvalid (s_axis_tvalid),
        .s_axis_tready (s_axis_tready),
        .s_axis_tlast  (s_axis_tlast),

        .m_axis_tdata  (m_axis_tdata),
        .m_axis_tvalid (m_axis_tvalid),
        .m_axis_tready (m_axis_tready),
        .m_axis_tlast  (m_axis_tlast)
    );

    // ============================================================
    // FIFO INIT (MENGHILANGKAN X / MERAH)
    // ============================================================
    always @(posedge aclk) begin
        if (!aresetn) begin
            for (i = 0; i < 256; i = i + 1)
                input_fifo[i] <= 0;
            wr_ptr <= 0;
            rd_ptr <= 0;
        end
        else begin
            if (s_axis_tvalid && s_axis_tready) begin
                input_fifo[wr_ptr] <= s_axis_tdata;
                wr_ptr <= wr_ptr + 1;
            end
        end
    end

    // ============================================================
    // STIMULUS
    // ============================================================
    initial begin
        s_axis_tdata  = 0;
        s_axis_tvalid = 0;
        s_axis_tlast  = 0;
        m_axis_tready = 1;
        sent_samples  = 0;
        recv_samples  = 0;

        #100;
        aresetn = 1;
        repeat(5) @(posedge aclk);

        $display("\n--- START PCM FORMATTER TEST ---");

        for (sent_samples = 0; sent_samples < TOTAL_SAMPLES; sent_samples = sent_samples + 1) begin
            test_val = 0.1 + sent_samples * 0.025;

            @(posedge aclk);
            while (!s_axis_tready)
                @(posedge aclk);

            s_axis_tdata  = $rtoi(test_val * Q30_F);
            s_axis_tvalid = 1;
            s_axis_tlast  = (sent_samples == TOTAL_SAMPLES-1);

            @(posedge aclk);
            s_axis_tvalid = 0;
            s_axis_tlast  = 0;
        end

        #500;
        $display("\n--- FINISH ---");
        $finish;
    end

    // ============================================================
    // OUTPUT MONITOR (TRANSACTION-BASED)
    // ============================================================
    always @(posedge aclk) begin
        if (m_axis_tvalid && m_axis_tready) begin
            $display("sample %02d : Q30 = %h (%0.3f) | PCM = %h (%0.3f) | TLAST = %b",
                recv_samples,
                input_fifo[rd_ptr],
                $signed(input_fifo[rd_ptr]) / Q30_F,
                m_axis_tdata,
                $signed(m_axis_tdata) / PCM_F,
                m_axis_tlast
            );

            rd_ptr <= rd_ptr + 1;
            recv_samples <= recv_samples + 1;
        end
    end

endmodule
