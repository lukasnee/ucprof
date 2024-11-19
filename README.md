# ucprof

Microcontroller C/C++ runtime execution profiling toolkit using GNU instrumentation calls, SEGGER RTT and 🔬speedscope.

## Usage

0. To use this library, you need `JLinkRTTLogger` from the [J-Link Software and
   Documentation Pack](https://www.segger.com/downloads/jlink/). There is are
   releases available for Linux.

1. Build and flash the firmware to the target MCU.

2. Ensure JLink is connected, run the device and launch the `JLinkRTTLogger`:

    ```bash
    sudo JLinkRTTLogger -Device STM32H750VB -If SWD -Speed 4000 -RTTChannel 2 ucprof.dat
    ```

3. Generate symbols file:

    ```bash
    arm-none-eabi-nm -lnC .build/platform/STM32H750/STM32H750 > .build/platform/STM32H750/STM32H750.symbols
    ```

4. Fold stacks of all thread calls in `ucprof.dat` record and export a Speedscope JSON for each thread:

    ```bash
    python3 ucprof.py .build/platform/STM32H750/STM32H750.symbols ucprof.dat
    ```

5. Open `ucprof_*.json`  in [Speedscope](https://www.speedscope.app/).

    > The `ucprof_0.json` will be the thread with the most stack calls, and the `ucprof_1.json` will be the second most, and so on.
