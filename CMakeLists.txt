cmake_minimum_required(VERSION 3.15)

project(
  ucprof
  VERSION 0.0.1
  LANGUAGES C CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(extern/SystemView_Src_V352a)

add_subdirectory(src)
