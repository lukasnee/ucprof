option(SEGGER_SYSVIEW_ENABLED "SEGGER SystemView switch" ON)
message(STATUS "SEGGER_SYSVIEW_ENABLED: ${SEGGER_SYSVIEW_ENABLED}")

if(NOT TARGET SeggerSysView_config)
  message(FATAL_ERROR "SeggerSysView_config target is not defined.\n")
endif()

if(SEGGER_SYSVIEW_ENABLED)
  add_library(SeggerSysView STATIC)
  target_sources(
    SeggerSysView
    PRIVATE SEGGER/SEGGER_RTT_ASM_ARMv7M.S SEGGER/SEGGER_RTT_printf.c
            SEGGER/SEGGER_RTT.c SEGGER/SEGGER_SYSVIEW.c
  )
  target_include_directories(SeggerSysView PUBLIC SEGGER Config)
  target_compile_definitions(SeggerSysView PUBLIC -DSEGGER_SYSVIEW_ENABLED)
  target_link_libraries(SeggerSysView PUBLIC SeggerSysView_config)
else()
  add_library(SeggerSysView INTERFACE)
  target_include_directories(SeggerSysView INTERFACE SYSVIEW_DISABLED Config)
  target_link_libraries(SeggerSysView INTERFACE SeggerSysView_config)
endif()
