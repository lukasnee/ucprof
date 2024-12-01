/*
Copyright (C) Lukas Neverauskis (@lukasnee) 2024

Distributed under the MIT License. For terms and conditions see LICENSE file or
http://opensource.org/licenses/MIT.
*/

#pragma once

#ifdef SEGGER_SYSVIEW_ENABLED

/**
 * @brief Initialize ucprof
 * @return int
 * @retval >= 0 - O.K.
 * @retval < 0 - Error
 */
int ucprof_init();

#else

#define ucprof_init() 0

#endif