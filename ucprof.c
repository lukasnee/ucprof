/*
Copyright (C) Lukas Neverauskis (@lukasnee) 2024

Distributed under the MIT License. For terms and conditions see LICENSE file or
http://opensource.org/licenses/MIT.
*/

#include "ucprof/ucprof.h"

#include "ucprof/ucprof_config_default.h"
#include "ucprof_config.h"

#include "SEGGER_RTT.h"

#include "FreeRTOS.h"

#include <stdint.h>

const unsigned ucprof_rtt_buffer_idx = 2;

void __cyg_profile_func_enter(void *this_fn, void *call_site) {
    if (xPortIsInsideInterrupt()) {
        return;
    }
    SEGGER_RTT_LOCK();
    static const unsigned char label[4] = {'O', 0, 0, 0};
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &label, 4);
    const uint32_t timestamp = SEGGER_SYSVIEW_GET_TIMESTAMP();
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &timestamp, 4);
    const uint32_t context = (uint32_t)xTaskGetCurrentTaskHandle();
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &context, 4);
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &this_fn, 4);
    SEGGER_RTT_UNLOCK();
}

void __cyg_profile_func_exit(void *this_fn, void *call_site) {
    if (xPortIsInsideInterrupt()) {
        return;
    }
    SEGGER_RTT_LOCK();
    static const unsigned char label[4] = {'C', 0, 0, 0};
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &label, 4);
    const uint32_t timestamp = SEGGER_SYSVIEW_GET_TIMESTAMP();
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &timestamp, 4);
    const uint32_t context = (uint32_t)xTaskGetCurrentTaskHandle();
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &context, 4);
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &this_fn, 4);
    SEGGER_RTT_UNLOCK();
}

uint8_t ucprof_rtt_buffer[UCPROF_CONFIG_RTT_BUFFER_SIZE];

int ucprof_init() {
    return SEGGER_RTT_ConfigUpBuffer(rtt_buffer_index, "ucprof", ucprof_rtt_buffer, sizeof(ucprof_rtt_buffer),
                                     SEGGER_RTT_MODE_NO_BLOCK_TRIM);
}
