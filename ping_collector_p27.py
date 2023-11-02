import socket
import struct
import select
import httplib  # Changed from http.client
import json
from datetime import datetime, timedelta

# Backporting statistics module (mean, median, stdev, quantiles)
import math
import os
import time

def mean(data):
    return sum(data) / float(len(data))

def median(data):
    sorted_data = sorted(data)
    n = len(data)
    if n % 2 == 1:
        return sorted_data[n//2]
    else:
        return (sorted_data[n//2 - 1] + sorted_data[n//2]) / 2.0

def stdev(data):
    avg = mean(data)
    variance = sum((x - avg) ** 2 for x in data) / (len(data) - 1)
    return math.sqrt(variance)

def quantiles(data, n=4):
    data = sorted(data)
    q = [0] * n
    for i in range(1, n):
        q[i-1] = data[int(math.ceil(i * len(data) / float(n))) - 1]
    q[n-1] = data[-1]
    return q

def print_stats(data):
    # Convert the ping results to milliseconds
    ping_times = [(received_time - sent_time).total_seconds() * 1000 for sent_time, received_time in data]
    
    # Calculate the statistics
    max_ping = max(ping_times)
    min_ping = min(ping_times)
    avg_ping = mean(ping_times)
    median_ping = median(ping_times)
    std_dev_ping = stdev(ping_times)
    q1 = quantiles(ping_times, n=4)[0]  # First quartile (25th percentile)
    q3 = quantiles(ping_times, n=4)[2]  # Third quartile (75th percentile)
    iqr = q3 - q1  # Interquartile Range
    
    # Print the statistics
    print "\nPing Statistics for Main Test:"
    print "  - Max Ping: %.2f milliseconds" % max_ping
    print "  - Min Ping: %.2f milliseconds" % min_ping
    print "  - Average Ping: %.2f milliseconds" % avg_ping
    print "  - Median Ping: %.2f milliseconds" % median_ping
    print "  - Standard Deviation: %.2f milliseconds" % std_dev_ping
    print "  - Interquartile Range: %.2f milliseconds\n" % iqr

def checksum(source_string):
    """
    Calculate the checksum of the input bytes.
    """
    sum = 0
    max_count = (len(source_string) // 2) * 2
    count = 0
    while count < max_count:
        val = ord(source_string[count + 1])*256 + ord(source_string[count])
        sum = sum + val
        sum = sum & 0xffffffff
        count = count + 2

    if max_count < len(source_string):
        sum = sum + ord(source_string[len(source_string) - 1])
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
    connection = httplib.HTTPSConnection(host)

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
            print "Data sent to Marius, Marius is happy"
            print response_json["joke"]
        else:
            print "Received a response without a joke."
    else:
        print "That didn't work, Marius don't worry, Marius probably don't need more data"

def create_packet(id, size=59):
    """
    Create a new echo request packet based on the given "id" and with a payload of the given size.
    """
    header = struct.pack("bbHHh", 8, 0, 0, id, 1)
    data = size * "Q"
    my_checksum = checksum(header + data)
    header = struct.pack("bbHHh", 8, 0, socket.htons(my_checksum), id, 1)
    return header + data

def ping(host):
    """
    Send a single ping to the given host and return the timestamps.
    """
    icmp = socket.getprotobyname("icmp")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, icmp)
        sock.settimeout(2.0)  # Timeout of 2 seconds
    except socket.error as e:
        if e.errno == 1:
            e.msg += " - Note that ICMP messages can only be sent from processes running as root."
            raise socket.error(e.msg)
    except Exception as e:
        print "Exception: " + str(e)
        return None

    my_id = int((datetime.now().microsecond & 0xFFFF))
    packet = create_packet(my_id)
    sent_time = datetime.now()
    sock.sendto(packet, (host, 1))
    
    while True:
        ready = select.select([sock], [], [], 2)
        if ready[0] == []:
            return None  # If timeout occurs, return None

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
        print "Pinging %s..." % region
        results, frequency = ping_server(host, sample_size)
        all_results[region] = results  # Store results for each region correctly
        if results:
            avg_ping = sum((r[1] - r[0]).total_seconds() for r in results) / len(results)
            print "%s average ping: %.3f seconds, frequency: %.2f pings/sec" % (region, avg_ping, frequency)
            if min_avg_ping is None or avg_ping < min_avg_ping:
                min_avg_ping = avg_ping
                best_region = region
    return best_region

def save_results_to_file(all_results, file_name):
    with open(file_name, 'w') as file:
        for region, results in all_results.items():
            file.write("Region: %s\n" % region)
            for sent_time, received_time in results:
                file.write("Sent: %s, Received: %s\n" % (sent_time, received_time))
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
    slack_minutes = 4  # Slack time for network fluctuations
    all_results = {}  # Dictionary to store all results
    print "Finding lowest ping server..."
    best_region = find_best_region(regions, sample_size, all_results)
    if best_region is not None:
        print "\nBest Region Analysis:"
        print "  - The best region is %s with the lowest average ping." % best_region
        _, frequency = ping_server(regions[best_region], sample_size)
        print "  - Approximate frequency: %.2f pings/sec\n" % frequency
        
        # Calculate approximate sample size for the desired duration
        approx_sample_size = int(frequency * 60 * duration_minutes)
        start_time = datetime.now()
        estimated_end_time = start_time + timedelta(minutes=duration_minutes)
        estimated_end_time_min = estimated_end_time - timedelta(minutes=slack_minutes)
        estimated_end_time_max = estimated_end_time + timedelta(minutes=slack_minutes)
        print "Pinging %s for an approximate duration of %d minutes..." % (best_region, duration_minutes)
        print "Don't do anything, but if you want to cancel, you can with Ctrl+C"
        print "  - Start time: %s" % start_time.strftime('%Y-%m-%d %H:%M:%S')
        print "  - Estimated end time: Between %s and %s\n" % (estimated_end_time_min.strftime('%Y-%m-%d %H:%M'), estimated_end_time_max.strftime('%Y-%m-%d %H:%M'))
        
        results, _ = ping_server(regions[best_region], approx_sample_size)
        all_results[best_region] = results  # Store the main check results
        
        # Check if any log file for the current hour already exists
        current_hour = time.strftime("%H")
        log_file_exists = any(
            current_hour == file[22:24] and file.endswith('.txt') and 'ping_results' in file
            for file in os.listdir('.')
        )

        # Store the results in a file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = "ping_results_%s.txt" % timestamp
        save_results_to_file(all_results, file_name)  # Save all results
        
        print "\nResults Summary:"
        print "  - All results saved to %s" % file_name
        print "  - Best region: %s\n" % best_region
        print_stats(results)  # Print statistics for the main check
        
        if log_file_exists:
            print "Marius did not need this log file, because it was within the same hour."
            print "If you want another joke, wait until the next hour."
        else:
            send_file(file_name)

    else:
        print "\nError:"
        print "  - Could not determine the best region due to ping failures.\n"

if __name__ == "__main__":
    main()
