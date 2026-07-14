# XIOPATH Headless CLI Worker Node

This node grabs Zero-Shot DOM Inference requests from the central XIOPATH server and processes them locally by spinning up a headless instance of the `agy` CLI!

## Prerequisites
1. Python 3.9+
2. The `agy` CLI must be installed and authenticated on this machine. If you are an admin and have used `agy` in your terminal before, you are already good to go!

## Quickstart
1. Install the single dependency:
   `pip install -r requirements.txt`
2. Run the worker:
   `python main.py`

This will establish a WebSocket connection to the central server. When a DOM inference request is received, it will automatically spawn `agy --print [prompt]` to generate the structured action!
