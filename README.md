# ucprof

Microcontroller C/C++ runtime execution profiling toolkit using GNU instrumentation calls, SEGGER RTT and 🔬speedscope.

## Usage

0. Build and flash the firmware to the target MCU.

1. Log RTT data to a file using `JLinkRTTLogger.exe`:

    ```bash
    sudo /mnt/c/Program\ Files/SEGGER/JLink_V794b/JLinkRTTLogger.exe -Device STM32H750VB -If SWD -Speed 4000 -RTTChannel 2 ucprof.dat
    ```

2. Generate symbols file:

    ```bash
    arm-none-eabi-nm -lnC .build/platform/STM32H750/STM32H750 > .build/platform/STM32H750/STM32H750.symbols
    ```

3. Fold stacks of all thread calls in `ucprof.dat` record and export a Speedscope JSON for each thread:

    ```bash
    python3 tools/ucprof/ucprof.py .build/platform/STM32H750/STM32H750.symbols ucprof.dat
    ```

4. Open `ucprof_*.json`  in [Speedscope](https://www.speedscope.app/).

    > The `ucprof_0.json` will be the thread with the most stack calls, and the `ucprof_1.json` will be the second most, and so on.
