#pragma once

/**
 * @brief SEGGER SystemView disabled definitions
 */

/*********************************************************************
 *
 *       Control and initialization functions
 */

#define SEGGER_SYSVIEW_Init(SysFreq, CPUFreq, pOSAPI, pfSendSysDesc)
#define SEGGER_SYSVIEW_Start()

/*********************************************************************
 *
 *       Event recording functions
 */

#define SEGGER_SYSVIEW_MarkStart(Id)
#define SEGGER_SYSVIEW_Mark(Id)
#define SEGGER_SYSVIEW_MarkStop(Id)
#define SEGGER_SYSVIEW_RecordEnterISR()
#define SEGGER_SYSVIEW_RecordExitISR()

/*********************************************************************
 *
 *       Application-provided functions
 */

#define SEGGER_SYSVIEW_Conf()
