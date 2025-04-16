/*
Copyright (C) Lukas Neverauskis (@lukasnee) 2024

Distributed under the MIT License. For terms and conditions see LICENSE file or
http://opensource.org/licenses/MIT.
*/

#include "ucprof/ucprof.h"

#include "ucprof/ucprof_config_default.h"
#include "ucprof_config.h"

#include "FreeRTOS.h"
#include "task.h"

#include "stm32h7xx_hal.h"

// TODO: research https://orbcode.org/orbuculum/swo-code-instrumentation/ and
// Orbuculum in general.

#define ITM_IS_ENABLED() ((ITM->TCR & ITM_TCR_ITMENA_Msk) != 0UL)
#define ITM_IS_PORT_ENABLED(port) ((ITM->TER & (1UL << (port))) != 0UL)

#define ITM_IS_PORT_READY(port) ITM_IS_ENABLED() && ITM_IS_PORT_ENABLED((port))

#define ITM_SEND_WORD(port, value)                                                                                             \
    while (ITM->PORT[(port)].u32 == 0UL) {                                                                                     \
        __NOP();                                                                                                               \
    }                                                                                                                          \
    ITM->PORT[(port)].u32 = (value)

#include <stdint.h>

#ifndef UNUSED
#define UNUSED(x) (void)(x)
#endif

// Attention: performance is of utmost importance
const uint8_t itm_port_trace = 0;

#pragma pack(push, 1)
typedef struct ucprof_packet_ {
    union {
        struct fields_t {
#define UCPROF_TYPE_ENTER 0
#define UCPROF_TYPE_EXIT 1
            uint32_t type : 1;
            uint32_t context : 7;
            uint32_t fn : 24; // MSB shall be provided by the other packet
            uint32_t cycle_count;
        } fields;
        uint32_t raw[2];
    };
} ucprof_packet_t;
#pragma pack(pop)

// Attention: performance is of utmost importance

static ucprof_packet_t ucprof_enter_packet = {
    .fields.type = UCPROF_TYPE_ENTER,
    .fields.context = 0,
    .fields.fn = 0,
    .fields.cycle_count = 0,
};

static ucprof_packet_t ucprof_exit_packet = {
    .fields.type = UCPROF_TYPE_EXIT,
    .fields.context = 0,
    .fields.fn = 0,
    .fields.cycle_count = 0,
};

void __cyg_profile_func_enter(void *this_fn, void *call_site) {
    UNUSED(call_site);
    if (xPortIsInsideInterrupt()) {
        return;
    }

    if (ITM_IS_PORT_READY(itm_port_trace)) {
        __disable_irq();
        ucprof_enter_packet.fields.context = uxTaskGetTaskNumber(xTaskGetCurrentTaskHandle());
        ucprof_enter_packet.fields.fn = (uint32_t)this_fn;
        ucprof_enter_packet.fields.cycle_count = DWT->CYCCNT;
        ITM_SEND_WORD(itm_port_trace, ucprof_enter_packet.raw[0]);
        ITM_SEND_WORD(itm_port_trace, ucprof_enter_packet.raw[1]);
        __enable_irq();
    }
}

void __cyg_profile_func_exit(void *this_fn, void *call_site) {
    UNUSED(call_site);
    if (xPortIsInsideInterrupt()) {
        return;
    }
    if (ITM_IS_PORT_READY(itm_port_trace)) {
        __disable_irq();
        ucprof_exit_packet.fields.context = uxTaskGetTaskNumber(xTaskGetCurrentTaskHandle());
        ucprof_exit_packet.fields.fn = (uint32_t)this_fn;
        ucprof_exit_packet.fields.cycle_count = DWT->CYCCNT;
        ITM_SEND_WORD(itm_port_trace, ucprof_exit_packet.raw[0]);
        ITM_SEND_WORD(itm_port_trace, ucprof_exit_packet.raw[1]);
        __enable_irq();
    }
}

void ucprof_init() {}
