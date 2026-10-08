#pragma once

#ifndef APRIS_ROVER_ENABLED
#define APRIS_ROVER_ENABLED 0
#endif

#if APRIS_ROVER_ENABLED
#if !__has_include("apris_rover_secrets.h")
#error "APRIS build requires ROS_Driver/apris_rover_secrets.h"
#endif
#include "apris_rover_secrets.h"
#endif
