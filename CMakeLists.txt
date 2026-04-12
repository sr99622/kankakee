cmake_minimum_required(VERSION 3.20)

project(kankakee VERSION 1.0.4 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_CXX_FLAGS
    "${CMAKE_CXX_FLAGS} -DSOCKLEN_T=socklen_t -D__STDC_CONSTANT_MACROS"
)

include(GNUInstallDirs)

if(WIN32)
    add_compile_options("/EHsc")
    add_compile_definitions(NO_GETIFADDRS)
    set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS TRUE)
    set(BUILD_SHARED_LIBS TRUE)
endif()

set(PYBIND11_FINDPYTHON ON)
find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(kankakee src/kankakee.cpp)

target_include_directories(kankakee PRIVATE include)

if(WIN32)
    target_link_libraries(kankakee PRIVATE
        wsock32
        ws2_32
    )
endif()

install(TARGETS kankakee
    LIBRARY DESTINATION kankakee
    RUNTIME DESTINATION kankakee
    ARCHIVE DESTINATION kankakee
)