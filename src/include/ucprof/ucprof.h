/*
Copyright (C) Lukas Neverauskis (@lukasnee) 2024

Distributed under the MIT License. For terms and conditions see LICENSE file or
http://opensource.org/licenses/MIT.
*/

#pragma once

#ifndef SEGGER_SYSVIEW_ENABLED

#define ucprof_init()

#else

/**
 * @brief Initialize ucprof
 * @return int
 * @retval >= 0 - O.K.
 * @retval < 0 - Error
 */
void ucprof_init();

#endif // SEGGER_SYSVIEW_ENABLED