option(SEGGER_SYSVIEW_ENABLED "SEGGER SystemView switch" ON)

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
  target_compile_options(SeggerSysView PUBLIC -finstrument-functions)
  target_compile_options(
    SeggerSysView
    PRIVATE
      -finstrument-functions-exclude-file-list=SEGGER/SEGGER_RTT_ASM_ARMv7M.S,SEGGER/SEGGER_RTT,SEGGER/SEGGER_RTT_printf,SEGGER/SEGGER_SYSVIEW,SEGGER/SYSVIEW
  )
else()
  add_library(SeggerSysView INTERFACE)
  target_include_directories(SeggerSysView INTERFACE SYSVIEW_DISABLED Config)
  target_link_libraries(SeggerSysView INTERFACE SeggerSysView_config)
endif()
