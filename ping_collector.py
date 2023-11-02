import socket
import struct
import select
import http.client
import json
from datetime import datetime, timedelta
import statistics
import os
import time

def print_stats(data):
    # Convert the ping results to milliseconds
    ping_times = [(received_time - sent_time).total_seconds() * 1000 for sent_time, received_time in data]
    
    # Calculate the statistics
    max_ping = max(ping_times)
    min_ping = min(ping_times)
    avg_ping = statistics.mean(ping_times)
    median_ping = statistics.median(ping_times)
    std_dev_ping = statistics.stdev(ping_times)
    q1 = statistics.quantiles(ping_times, n=4)[0]  # First quartile (25th percentile)
    q3 = statistics.quantiles(ping_times, n=4)[2]  # Third quartile (75th percentile)
    iqr = q3 - q1  # Interquartile Range
    
    # Print the statistics
    print("\nPing Statistics for Main Test:")
    print(f"  - Max Ping: {max_ping:.2f} milliseconds")
    print(f"  - Min Ping: {min_ping:.2f} milliseconds")
    print(f"  - Average Ping: {avg_ping:.2f} milliseconds")
    print(f"  - Median Ping: {median_ping:.2f} milliseconds")
    print(f"  - Standard Deviation: {std_dev_ping:.2f} milliseconds")
    print(f"  - Interquartile Range: {iqr:.2f} milliseconds\n")


def checksum(source_string):
    """
    Calculate the checksum of the input bytes.
    """
    sum = 0
    max_count = (len(source_string) // 2) * 2
    count = 0
    while count < max_count:
        val = source_string[count + 1]*256 + source_string[count]
        sum = sum + val
        sum = sum & 0xffffffff
        count = count + 2

    if max_count < len(source_string):
        sum = sum + source_string[len(source_string) - 1]
        sum = sum & 0xffffffff

    sum = (sum >> 16) + (sum & 0xffff)
    sum = sum + (sum >> 16)
    answer = ~sum
    answer = answer & 0xffff
    answer = answer >> 8 | (answer << 8 & 0xff00)
    return answer
def send_file(file_path):
    host = '0a6ejoevl3.execute-api.us-east-1.amazonaws.com'
    endpoint = '/prod/ping'

    # Read file contents
    with open(file_path, 'r') as file:
        file_content = file.read()

    # Setup connection
    connection = http.client.HTTPSConnection(host)

    # Headers
    headers = {'Content-type': 'application/text'}

    # Send POST request
    connection.request('POST', endpoint, body=file_content, headers=headers)

    # Get the response
    response = connection.getresponse()
    response_data = response.read()
    response_json = json.loads(response_data)

    # Check the response
    if response.status == 200:
        if "joke" in response_json:
            print("Deta sent to Marius, Marius is happy")
            print(response_json["joke"])
        else:
            print("Received a response without a joke.")
    else:
        print("That didn't work, Marius don't worry, Marius probably don't need more data")
        
def create_packet(id, size=59):
    """
    Create a new echo request packet based on the given "id" and with a payload of the given size.
    """
    header = struct.pack("bbHHh", 8, 0, 0, id, 1)
    data = size * "Q"
    my_checksum = checksum(header + data.encode('utf-8'))
    header = struct.pack("bbHHh", 8, 0, socket.htons(my_checksum), id, 1)
    return header + data.encode('utf-8')

def ping(host):
    """
    Send a single ping to the given host and return the timestamps.
    """
    icmp = socket.getprotobyname("icmp")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, icmp)
    except socket.error as e:
        if e.errno == 1:
            e.msg += " - Note that ICMP messages can only be sent from processes running as root."
            raise socket.error(e.msg)
    except Exception as e:
        print("Exception: " + str(e))
        return None

    my_id = datetime.now().microsecond & 0xFFFF
    packet = create_packet(my_id)
    sent_time = datetime.now()
    sock.sendto(packet, (host, 1))
    
    while True:
        ready = select.select([sock], [], [], 1)
        if ready[0] == []:
            return None

        time_received = datetime.now()
        rec_packet, addr = sock.recvfrom(1024)
        icmp_header = rec_packet[20:28]
        type, code, checksum, packet_id, sequence = struct.unpack("bbHHh", icmp_header)
        if packet_id == my_id:
            return (sent_time, time_received)


def ping_server(host, sample_size):
    """
    Ping the server and return timestamps for a given number of samples.
    """
    results = []
    start_time = datetime.now()
    for _ in range(sample_size):
        result = ping(host)
        if result:
            results.append(result)
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    frequency = sample_size / duration if duration > 0 else 0
    return results, frequency

def find_best_region(regions, sample_size, all_results):
    min_avg_ping = None
    best_region = None
    for region, host in regions.items():
        print(f"Pinging {region}...")
        results, frequency = ping_server(host, sample_size)
        all_results[region] = results  # Store results for each region correctly
        if results:
            avg_ping = sum((r[1] - r[0]).total_seconds() for r in results) / len(results)
            print(f"{region} average ping: {avg_ping:.3f} seconds, frequency: {frequency:.2f} pings/sec")
            if min_avg_ping is None or avg_ping < min_avg_ping:
                min_avg_ping = avg_ping
                best_region = region
    return best_region


def save_results_to_file(all_results, file_name):
    with open(file_name, 'w') as file:
        for region, results in all_results.items():
            file.write(f"Region: {region}\n")
            for sent_time, received_time in results:
                file.write(f"Sent: {sent_time}, Received: {received_time}\n")
            file.write("\n")



def main():
    regions = {
        "NA-East": "ping-nae.ds.on.epicgames.com",
        "NA-Central": "ping-nac.ds.on.epicgames.com",
        "NA-West": "ping-naw.ds.on.epicgames.com",
        "Europe": "ping-eu.ds.on.epicgames.com",
        "Oceania": "ping-oce.ds.on.epicgames.com",
        "Brazil": "ping-br.ds.on.epicgames.com",
        "Asia": "ping-asia.ds.on.epicgames.com"
    }
    sample_size = 10
    duration_minutes = 10  # Duration for the main check in minutes
    all_results = {}  # Dictionary to store all results
    print("Finding lowest ping server...")
    best_region = find_best_region(regions, sample_size, all_results)
    if best_region is not None:
        print("\nBest Region Analysis:")
        print(f"  - The best region is {best_region} with the lowest average ping.")
        _, frequency = ping_server(regions[best_region], sample_size)
        print(f"  - Approximate frequency: {frequency:.2f} pings/sec\n")
        
        # Calculate approximate sample size for the desired duration
        approx_sample_size = int(frequency * 60 * duration_minutes)
        start_time = datetime.now()
        estimated_end_time = start_time + timedelta(minutes=duration_minutes)
        print(f"Pinging {best_region} for an approximate duration of {duration_minutes} minutes...")
        print("Don't do anything, but if you want to cancel, you can with Ctrl+C")
        print(f"  - Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  - Estimated end time: {estimated_end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        results, _ = ping_server(regions[best_region], approx_sample_size)
        all_results[best_region] = results  # Store the main check results
        

        print(f"\nResults Summary:")
        print(f"  - All results saved to {file_name}")
        print(f"  - Best region: {best_region}\n")
        print_stats(results)  # Print statistics for the main check
        # Get only the current hour
        current_hour = time.strftime("%H")

        # Check for existing log files with the same format
        log_files = [f for f in os.listdir() if f.endswith('.txt') and 'ping_results' in f]

        # Check if any log file for the current hour already exists
        for file in log_files:
            if current_hour == file[22:24]:
                
                log_file_exists = True
                break
            else:
                log_file_exists = False
                
        # Store the results in a file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"ping_results_{timestamp}.txt"
        save_results_to_file(all_results, file_name)  # Save all results
        
        if log_file_exists:
            print(f"Marius did not need this log file, because it was within the same hour.")
            print("If you want another joke, wait until the next hour.")
        else:
            send_file(file_name)

    else:
        print("\nError:")
        print("  - Could not determine the best region due to ping failures.\n")

if __name__ == "__main__":
    main()