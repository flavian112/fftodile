// Copyright (c) 2026 ETH Zurich and University of Bologna.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
//
// Authors:
// - Flavian Kaufmann
// - Thanu Kanagalingam

// Test: 16-point FFT accelerator correctness.
//
// Runs several deterministic vectors through the hardware accelerator and
// compares the packed {real[15:0], imag[15:0]} results against a software model
// with the same fixed-point twiddles and one right shift per butterfly stage.

#include "uart.h"
#include "print.h"
#include "util.h"
#include "fft.h"
#include "config.h"

// Twiddle factors W_k = exp(-j*2*pi*k/16), stored as {cos_k, sin_k}.
// Values match rtl/user_domain/fft_core/fft_iterative.sv.
static const int16_t tw16[16] = {
    32767, 0, 30274, 12540, 23170, 23170, 12540, 30274, 0, 32767, -12540, 30274, -23170, 23170, -30274, 12540,
};

// Static buffers in SRAM. 2 x 16 x 4 = 128 bytes.
static volatile fft_sample_t in_buf[FFT_N];
static volatile fft_sample_t out_buf[FFT_N];
static fft_sample_t exp_buf[FFT_N];

static void fft_sw_inplace(fft_sample_t *buf) {
    // Bit-reverse permutation (4-bit index reversal for N=16).
    for (int i = 1, j = 0; i < FFT_N; i++) {
        int bit = FFT_N >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
            fft_sample_t t = buf[i];
            buf[i]         = buf[j];
            buf[j]         = t;
        }
    }

    for (int half = 1; half < FFT_N; half <<= 1) {
        int span = half << 1;
        int step = FFT_N / span;
        for (int k = 0; k < FFT_N; k += span) {
            for (int j = 0; j < half; j++) {
                int ti            = (j * step) << 1;
                int16_t c         = tw16[ti];
                int16_t s         = tw16[ti + 1];

                fft_sample_t va   = buf[k + j];
                fft_sample_t vb   = buf[k + j + half];
                int16_t ar        = fft_real(va);
                int16_t ai        = fft_imag(va);
                int16_t br        = fft_real(vb);
                int16_t bi        = fft_imag(vb);

                int32_t wr        = ((int32_t)c * br + (int32_t)s * bi) >> 15;
                int32_t wi        = ((int32_t)c * bi - (int32_t)s * br) >> 15;

                buf[k + j]        = fft_pack((int16_t)((ar + wr) >> 1), (int16_t)((ai + wi) >> 1));
                buf[k + j + half] = fft_pack((int16_t)((ar - wr) >> 1), (int16_t)((ai - wi) >> 1));
            }
        }
    }
}

static int run_fft_vector(const fft_sample_t *input, int ret_base) {
    for (int i = 0; i < FFT_N; i++) {
        in_buf[i]  = input[i];
        out_buf[i] = 0xA5A50000u | (uint32_t)i;
        exp_buf[i] = input[i];
    }

    fft_sw_inplace(exp_buf);
    fft_run((const fft_sample_t *)in_buf, (fft_sample_t *)out_buf);

    CHECK_ASSERT(ret_base + 1, fft_done());
    CHECK_ASSERT(ret_base + 2, !fft_busy());

    for (int k = 0; k < FFT_N; k++) {
        CHECK_ASSERT(ret_base + 10 + k, out_buf[k] == exp_buf[k]);
    }

    return 0;
}

int main() {
    uart_init();

    // --- Write/readback register tests ---
    fft_write_reg(FFT_SRC_ADDR_OFFSET, 0x10000100);
    CHECK_ASSERT(1, fft_read_reg(FFT_SRC_ADDR_OFFSET) == 0x10000100);

    fft_write_reg(FFT_DST_ADDR_OFFSET, 0x10000200);
    CHECK_ASSERT(2, fft_read_reg(FFT_DST_ADDR_OFFSET) == 0x10000200);

    // FFT accelerator should be idle after reset (STATUS = 0).
    CHECK_ASSERT(3, fft_status() == 0);

    static const fft_sample_t impulse_at_0[FFT_N] = {
        FFT_SAMPLE(0x1000, 0), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    };
    static const fft_sample_t impulse_at_3[FFT_N] = {
        0, 0, 0, FFT_SAMPLE(0x1000, 0), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    };
    static const fft_sample_t dc_real[FFT_N] = {
        FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0),
        FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0),
        FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0),
        FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0), FFT_SAMPLE(0x0400, 0),
    };
    static const fft_sample_t alternating_real[FFT_N] = {
        FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0), FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0),
        FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0), FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0),
        FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0), FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0),
        FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0), FFT_SAMPLE(0x0800, 0), FFT_SAMPLE(-0x0800, 0),
    };
    static const fft_sample_t mixed_complex[FFT_N] = {
        FFT_SAMPLE(1200, -300), FFT_SAMPLE(-900, 700), FFT_SAMPLE(300, 1100), FFT_SAMPLE(-120, -950),
        FFT_SAMPLE(2047, 0),    FFT_SAMPLE(-2048, 63), FFT_SAMPLE(512, -512), FFT_SAMPLE(-256, 1536),
        FFT_SAMPLE(0, -1700),   FFT_SAMPLE(77, 88),    FFT_SAMPLE(-333, 444), FFT_SAMPLE(999, -111),
        FFT_SAMPLE(-1500, 120), FFT_SAMPLE(640, -321), FFT_SAMPLE(-42, -43),  FFT_SAMPLE(1700, 900),
    };
    static const fft_sample_t small_values[FFT_N] = {
        FFT_SAMPLE(1, 0),   FFT_SAMPLE(0, 1),   FFT_SAMPLE(-1, 0),  FFT_SAMPLE(0, -1),
        FFT_SAMPLE(2, -2),  FFT_SAMPLE(-2, 2),  FFT_SAMPLE(3, 4),   FFT_SAMPLE(-3, -4),
        FFT_SAMPLE(5, -6),  FFT_SAMPLE(-5, 6),  FFT_SAMPLE(7, 8),   FFT_SAMPLE(-7, -8),
        FFT_SAMPLE(9, -10), FFT_SAMPLE(-9, 10), FFT_SAMPLE(11, 12), FFT_SAMPLE(-11, -12),
    };

    CHECK_CALL(run_fft_vector(impulse_at_0, 100));
    CHECK_CALL(run_fft_vector(impulse_at_3, 200));
    CHECK_CALL(run_fft_vector(dc_real, 300));
    CHECK_CALL(run_fft_vector(alternating_real, 400));
    CHECK_CALL(run_fft_vector(mixed_complex, 500));
    CHECK_CALL(run_fft_vector(small_values, 600));

    // Run the first vector again to catch stale DONE/BUSY state across back-to-back jobs.
    CHECK_CALL(run_fft_vector(impulse_at_0, 700));

    return 0;
}
