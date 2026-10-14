# UnoReality 🥽
README BUILT  BY AI

UnoReality is an open-source DIY Virtual Reality headset project that brings SteamVR PCVR to the ESP32-P4 microcontroller[cite: 1]. It bridges low-cost hardware with full PCVR gaming, allowing you to stream VR displays, track head/hand movements, and use controllers via SteamVR.

## 🛠️ Prerequisites

To keep your system clean, we only install exactly what is needed to make the headset communicate with SteamVR.

1. **Python 3.8+** 
2. **Steam & SteamVR** (Installed via Steam)
3. **VMT (Virtual Motion Tracker)** - Essential for tracking your headset and controllers in SteamVR without official base stations.

## 🪫 Components

1. **ESP32-P4**
2. **MPU-6050 6-Axis**
3. **Any Arduino speaker but preferrably "Mini Loudspeaker"

### Python Dependencies
Install the required base libraries using `pip`:
```bash
pip install pyserial
```

(Install any other specific libraries prompted when running the Python scripts, but the core relies on standard socket/serial communication).
🚀 Setting Up VMT & SteamVR

To get SteamVR to recognize the UnoReality headset and allow you to play with a standard controller, follow these steps:

    Install VMT:

        Download the latest release of Virtual Motion Tracker (VMT).

        Follow their installation instructions to register the driver with SteamVR.

    Configure SteamVR:

        Open SteamVR.

        Go to Settings > Startup / Standby > Manage Add-Ons and ensure vmt is set to On.

    Connect the Headset:

        Flash firmware.cpp to your ESP32-P4.

        Run the UnoReality Python bridge scripts (e.g., vrdisplay.py and tt.py) to establish the connection.

    Playing with a Controller:

        Once VMT detects the headset, launch a SteamVR game.

        Connect a standard Xbox or Bluetooth controller to your PC. SteamVR will map this to standard VR inputs for seated or gamepad-compatible VR games.

🧠 Codebase & AI Assistance (Vibecoding)

This project was built with a mix of manual engineering and AI assistance (vibecoding) to accelerate development.

    The Core Logic: The core templates, logic, and hardware routing were designed manually.

    Partially AI-Assisted Scripts: The following scripts were built by manually writing the template and architecture, while AI was used to flesh out the boilerplate and complete the remaining functions. They are not fully AI-generated:

        firmware.cpp

        audio.py

    Fully AI-Generated:

        tt.py — This bridge script was fully vibecoded because the specific hardware wasn't available for local testing at the time of writing, allowing the project structure to proceed.

🤝 Contributing (Help needed with firmware.cpp!)

Contributions are highly encouraged! Because I didn't have the exact hardware on hand to test everything locally, firmware.cpp is currently untested on a physical ESP32-P4.

If you have the hardware, please feel free to test, debug, and fix the firmware. If you make improvements or fix bugs, submit a Pull Request (PR) on GitHub with your code so it can be reviewed and merged into the main project.
📄 License

This project is licensed under the MIT License. You are completely free to use, modify, and distribute this code. However, if you want your changes to become part of the official UnoReality repository, you must submit a Pull Request.



README BUILT  BY AI
