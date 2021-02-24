GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
info() {
    printf "${GREEN}$@${NC}\n"
}
error() {
    printf "${RED}$@${NC}\n"
}

alias source=.
printf "${GREEN}Prepaing build ${JOB_NAME}:${BUILD_NUMBER} on ${NODE_NAME}:${EXECUTOR_NUMBER} at ${JENKINS_URL} in directory ${WORKSPACE}${NC}"
mkdir -p project
if [ -f "submission_file" ]; then
    info "submission received."
else
	error "missing a submission file!"
    exit 1
fi

if [ -z "${NETWORK_NAME}" ]; then
	error "NETWORK_NAME not specified!"
    exit 2
	
else
	info "NETWORK_NAME = ${NETWORK_NAME}"
fi

tar -xzf submission_file -C project
info "Submission extracted"
mkdir -p project/build
cd project/build
source /scratch/jenkins_master/streamblocks_init

info "XILINX_XRT = ${XILINX_XRT}"
info "XILINX_VITIS = ${XILINX_VITIS}"
info "XILINX_VIVADO = ${XILINX_VIVADO}"
info "Configuring the build"
configs="-DUSE_VITIS=on -DPLATFORM=${PLATFORM} -DTARGET=${TARGET} -DFPGA_NAME=${FPGA_NAME} -DHLS_CLOCK_PERIOD=${HLS_CLOCK_PERIOD} -DKERNEL_FREQ=${KERNEL_FREQ} -DIS_MPSOC=${IS_MPSOC}"
if [ "$IS_MPSOC" = "true" ]; then
	configs="$configs -DMPSOC_CLOCK_ID=${MPSOC_CLOCK_ID}"
fi
cmake .. $configs

if [ "${SC_MODE}" = false ]; then
    
    # Build FPGA binary
    info "Making XO"
    make ${NETWORK_NAME}_kernel_xo -j 4
    info "Making xclbin"
    make ${NETWORK_NAME}_kernel_xclbin -j
    info "XCLBIN build done!"
    cd ../bin/
    tar -czf ${JOB_NAME}_${BUILD_NUMBER}_xclbin.tar.gz xclbin
    info "xclbin available at ${WORKSPACE}/project/bin/${JOB_NAME}_${BUILD_NUMBER}_xclbin.tar.gz"

else

    # Build and run the systemc binary
    if [ -f "../vivado-hls/systemc"]; then
        info "Bulding systemc co-simulation binary"
        make ${NETWORK_NAME} -j
        cd ../bin
        info "Executing simulation"
        ./${NETWORK_NAME} --hardware-profile systemc-profile.xml
    else 
        error "SystemC source files not found! Are you sure this is a systemc project?"
        exit 3
    fi
fi



