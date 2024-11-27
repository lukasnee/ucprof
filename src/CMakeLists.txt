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

add_library(ucprof STATIC)

target_sources(ucprof PRIVATE ucprof.c)

target_include_directories(
  ucprof PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include ${UCPROF_CONFIG_DIR}
)

target_compile_options(
  ucprof PRIVATE -finstrument-functions-exclude-file-list=ucprof.c
)
