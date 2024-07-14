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

#pragma pack(push, 1)
typedef struct profile_packet_ {
    unsigned char label[4];
    uint32_t timestamp;
    uint32_t context;
    void *this_fn;
} profile_packet_t;
#pragma pack(pop)

// Attention: performance is of utmost importance

static profile_packet_t enter_profile_packet_buff = {{'O', '\0', '\0', '\0'}, 0, 0, 0};
static profile_packet_t exit_profile_packet_buff = {{'C', '\0', '\0', '\0'}, 0, 0, 0};

void __cyg_profile_func_enter(void *this_fn, void *call_site) {
    if (xPortIsInsideInterrupt()) {
        return;
    }
    SEGGER_RTT_LOCK();
    enter_profile_packet_buff.timestamp = SEGGER_SYSVIEW_GET_TIMESTAMP();
    enter_profile_packet_buff.context = (uint32_t)xTaskGetCurrentTaskHandle();
    enter_profile_packet_buff.this_fn = this_fn;
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &enter_profile_packet_buff, sizeof(enter_profile_packet_buff));
    SEGGER_RTT_UNLOCK();
}

void __cyg_profile_func_exit(void *this_fn, void *call_site) {
    if (xPortIsInsideInterrupt()) {
        return;
    }
    SEGGER_RTT_LOCK();
    exit_profile_packet_buff.timestamp = SEGGER_SYSVIEW_GET_TIMESTAMP();
    exit_profile_packet_buff.context = (uint32_t)xTaskGetCurrentTaskHandle();
    exit_profile_packet_buff.this_fn = this_fn;
    SEGGER_RTT_WriteNoLock(ucprof_rtt_buffer_idx, &exit_profile_packet_buff, sizeof(exit_profile_packet_buff));
    SEGGER_RTT_UNLOCK();
}

uint8_t ucprof_rtt_buffer[UCPROF_CONFIG_RTT_BUFFER_SIZE];

int ucprof_init() {
    return SEGGER_RTT_ConfigUpBuffer(ucprof_rtt_buffer_idx, "ucprof", ucprof_rtt_buffer, sizeof(ucprof_rtt_buffer),
                                     SEGGER_RTT_MODE_NO_BLOCK_TRIM);
}
