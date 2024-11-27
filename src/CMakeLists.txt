add_library(ucprof STATIC)

target_sources(${PROJECT_NAME}
    PRIVATE
        ucprof.c
)

target_include_directories(${PROJECT_NAME}
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        # "config.h" must be provided by the consuming project
        $<INSTALL_INTERFACE:include>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>

)

target_compile_options(${PROJECT_NAME}
    PRIVATE
        -finstrument-functions-exclude-file-list=${CMAKE_CURRENT_SOURCE_DIR}/ucprof.c
)
