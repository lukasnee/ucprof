option(SEGGER_SYSVIEW_ENABLED "SEGGER SystemView switch" ON)
message(STATUS "SEGGER_SYSVIEW_ENABLED: ${SEGGER_SYSVIEW_ENABLED}")

if(SEGGER_SYSVIEW_ENABLED)
  add_library(SysView STATIC)
  target_sources(
    SysView PRIVATE SEGGER/SEGGER_RTT_ASM_ARMv7M.S SEGGER/SEGGER_RTT_printf.c
                    SEGGER/SEGGER_RTT.c SEGGER/SEGGER_SYSVIEW.c
  )
  target_include_directories(SysView PUBLIC SEGGER Config)
  target_compile_definitions(SysView PUBLIC -DSEGGER_SYSVIEW_ENABLED)
else()
  add_library(SysView INTERFACE)
  target_include_directories(SysView INTERFACE SYSVIEW_DISABLED)
endif()
