# Configuring Smart Licensing for Cisco Smart Software Manager On-Prem
This scripts automates registration of devices to CSSM On-prem.

File _smart_license_config.txt_ shoould contain your specific configuration for Smart License registration to CSSM On-Prem. Instead of _`{{ CSSM_On_Prem_IP_Address }}`_ put IP address of your server.

To use the script - run _main.py_ and open your browser at http://127.0.0.1:5000/ 

Script does the following:
1. Connect to device -> continue if connection is successful.
2. Check device's licensing status and DLC status.
3. If device is not registered to CSSM On-Prem -> check reachability from device to CSSM On-Prem
4. If CSSM On-Prem is not reachable -> try reachability from diffrenet interfaces in GRT
5. Configure device with _smart_license_config.txt_
6. Wait for registration (120 seconds)
7. if device supports DLC and DLC not performed -> run DLC
