if(NOT TARGET ucprof_config)
  message(
    FATAL_ERROR
      "ucprof_config target is not defined.\n"
      "Please specify a cmake target that defines the include directory for\n"
      "ucprof_config.h:\n"
      "add_library(ucprof_config INTERFACE)\n"
      "target_include_directories(ucprof_config INTERFACE <path_to_ucprof_config.h>)\n"
  )
endif()

if(SEGGER_SYSVIEW_ENABLED)
  add_library(ucprof STATIC)
  target_sources(ucprof PRIVATE ucprof.c)
  target_include_directories(ucprof PUBLIC include)
  target_compile_options(
    ucprof PRIVATE -finstrument-functions-exclude-file-list=ucprof.c
  )
  target_link_libraries(ucprof PUBLIC FreeRTOS SeggerSysView ucprof_config)
else()
  add_library(ucprof INTERFACE)
  target_include_directories(ucprof INTERFACE include)
  target_link_libraries(ucprof INTERFACE FreeRTOS SeggerSysView ucprof_config)
endif()
