// Copyright (c) 2026 ETH Zurich and University of Bologna.
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0
//
// Authors:
// - Flavian Kaufmann
// - Thanu Kanagalingam

// Benchmark: compare the reference software FFT against the hardware accelerator.

#include "uart.h"
#include "print.h"
#include "util.h"
#include "fft.h"
#include "fft_ref.h"

typedef struct {
    uint32_t software_visible_cycles;
    uint32_t accelerator_cycles;
    uint32_t transfer_overhead_cycles;
    fft_sample_t bin0;
    fft_sample_t bin_mid;
} fft_benchmark_result_t;

static volatile fft_sample_t input_buffer[FFT_N];
static volatile fft_sample_t output_buffer[FFT_N];
static volatile fft_sample_t inplace_buffer[FFT_N];
static fft_sample_t software_buffer[FFT_N];

static void prepare_impulse_input(void) {
    for (int index = 0; index < FFT_N; index++) {
        input_buffer[index] = (index == 0) ? fft_pack(0x1000, 0) : 0u;
    }
}

static void copy_input_to_software_buffer(void) {
    for (int index = 0; index < FFT_N; index++) {
        software_buffer[index] = input_buffer[index];
    }
}

static void copy_input_to_inplace_buffer(void) {
    for (int index = 0; index < FFT_N; index++) {
        inplace_buffer[index] = input_buffer[index];
    }
}

static fft_benchmark_result_t benchmark_software_fft(void) {
    copy_input_to_software_buffer();

    uint32_t start_cycles = (uint32_t)get_mcycle();
    fft_ref_run(software_buffer);

    fft_benchmark_result_t result = {
        .software_visible_cycles  = (uint32_t)get_mcycle() - start_cycles,
        .accelerator_cycles       = 0,
        .transfer_overhead_cycles = 0,
        .bin0                     = software_buffer[0],
        .bin_mid                  = software_buffer[FFT_N / 2],
    };
    return result;
}

static fft_benchmark_result_t benchmark_hardware_fft(void) {
    uint32_t start_cycles = (uint32_t)get_mcycle();
    fft_run((const fft_sample_t *)input_buffer, (fft_sample_t *)output_buffer);

    uint32_t total_cycles         = (uint32_t)get_mcycle() - start_cycles;
    uint32_t accel_cycles         = fft_cycles();
    uint32_t transfer_overhead    = (total_cycles > accel_cycles) ? (total_cycles - accel_cycles) : 0;

    fft_benchmark_result_t result = {
        .software_visible_cycles  = total_cycles,
        .accelerator_cycles       = accel_cycles,
        .transfer_overhead_cycles = transfer_overhead,
        .bin0                     = output_buffer[0],
        .bin_mid                  = output_buffer[FFT_N / 2],
    };
    return result;
}

static fft_benchmark_result_t benchmark_hardware_fft_inplace(void) {
    copy_input_to_inplace_buffer();

    uint32_t start_cycles = (uint32_t)get_mcycle();
    fft_run((const fft_sample_t *)inplace_buffer, (fft_sample_t *)inplace_buffer);

    uint32_t total_cycles         = (uint32_t)get_mcycle() - start_cycles;
    uint32_t accel_cycles         = fft_cycles();
    uint32_t transfer_overhead    = (total_cycles > accel_cycles) ? (total_cycles - accel_cycles) : 0;

    fft_benchmark_result_t result = {
        .software_visible_cycles  = total_cycles,
        .accelerator_cycles       = accel_cycles,
        .transfer_overhead_cycles = transfer_overhead,
        .bin0                     = inplace_buffer[0],
        .bin_mid                  = inplace_buffer[FFT_N / 2],
    };
    return result;
}

static void print_software_result(fft_benchmark_result_t result) {
    printf("SW: 0x%x cycles  bin[0]=0x%x  bin[mid]=0x%x\n", result.software_visible_cycles, result.bin0,
           result.bin_mid);
}

static void print_hardware_result_out_of_place(fft_benchmark_result_t result) {
    printf("HW out-of-place: 0x%x cycles  bin[0]=0x%x  bin[mid]=0x%x\n", result.software_visible_cycles, result.bin0,
           result.bin_mid);
    printf("HW out-of-place accelerator: 0x%x cycles\n", result.accelerator_cycles);
    printf("HW out-of-place transfer+host overhead: 0x%x cycles\n", result.transfer_overhead_cycles);
}

static void print_hardware_result_in_place(fft_benchmark_result_t result) {
    printf("HW in-place: 0x%x cycles  bin[0]=0x%x  bin[mid]=0x%x\n", result.software_visible_cycles, result.bin0,
           result.bin_mid);
    printf("HW in-place accelerator: 0x%x cycles\n", result.accelerator_cycles);
    printf("HW in-place transfer+host overhead: 0x%x cycles\n", result.transfer_overhead_cycles);
}

int main(void) {
    uart_init();
    prepare_impulse_input();

    fft_benchmark_result_t software              = benchmark_software_fft();
    fft_benchmark_result_t hardware_out_of_place = benchmark_hardware_fft();
    fft_benchmark_result_t hardware_in_place     = benchmark_hardware_fft_inplace();

    printf("=== FFT Benchmark (N=0x%x, config=0x%x, 20 MHz) ===\n", FFT_N, fft_config());
    print_software_result(software);
    print_hardware_result_out_of_place(hardware_out_of_place);
    print_hardware_result_in_place(hardware_in_place);
    printf("Speedup (out-of-place): ~0x%x x\n",
           hardware_out_of_place.software_visible_cycles
               ? software.software_visible_cycles / hardware_out_of_place.software_visible_cycles
               : 0);
    printf("Speedup (in-place): ~0x%x x\n",
           hardware_in_place.software_visible_cycles
               ? software.software_visible_cycles / hardware_in_place.software_visible_cycles
               : 0);

    uart_write_flush();
    return 0;
}
