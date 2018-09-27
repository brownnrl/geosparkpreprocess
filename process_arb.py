# /usr/bin/evn python2

import os
import argparse
import pprint
import re
import csv
from collections import defaultdict
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


class ParseException(Exception):
    pass


DMS_RE = re.compile(r"(\d*)-(\d*)-(\d*\.?\d*)([NSEW])")


def parse_dms(dms_string):
    m = DMS_RE.match(dms_string)
    if m is None:
        raise ParseException("Doesn't match re: %s" % (dms_string,))
    degree = m.group(1)
    minutes = m.group(2)
    seconds = m.group(3)
    nsew = m.group(4)
    dms_double = float(degree) + float(minutes) / 60. + float(seconds) / 3600.
    if nsew in ('S', 'W'):
        return -1. * dms_double
    return dms_double


def convert_skyvec_rep(dms_string):
    m = DMS_RE.match(dms_string)
    if m is None:
        raise ParseException("Doesn't match re: %s" % (dms_string,))
    deg = m.group(1)
    min = m.group(2)
    sec = m.group(3)[0:m.group(3).find('.')] if '.' in m.group(3) else m.group(3)

    return deg + min + sec + m.group(4)


def main():
    parser = argparse.ArgumentParser(description='Process the ARTCC boundary file from subscription file.')
    parser.add_argument(dest='arb_file',
                        help='Location of the ARB.txt file within the NASR subscriber file')
    parser.add_argument(dest='out_file', default="FAVs_GeoJSON.csv")
    args = parser.parse_args()

    if not os.path.exists(args.arb_file):
        print "Path does not exist."
        return

    print "Reading from file", args.arb_file
    with open(args.arb_file, 'r') as f:
        content = f.read()

    # Example line that we want to process
    # ZAB *H*53855ALBUQUERQUE                             HIGH      35-46-00.0N   111-50-30.0W  /COMMON ZAB-ZDV-ZLA/TO                                                                                                                                                                                                                                                                                      000100

    # Example of an end of a boundary
    # ZAB *H*01373ALBUQUERQUE                             HIGH      35-24-00.0N   112-00-00.0W  TO POINT OF BEGINNING                                                                                                                                                                                                                                                                                       000760

    # The "TO POINT OF BEGINNING" tells us we wrap back to the start point

    # Example line that we want to exclude
    # ZAK *F*50060OAKLAND OCEANIC ARTCC                   FIR ONLY  21-00-00.0N   130-00-00.0E  /COMMON OAKLAND CTA/FIR-MANILA CTA/FIR/ FUKUOKA FIR TO                                                                                                                                                                                                                                                      002040


    # Our records are fixed width delimited, meaning each "field" is alloted a certain number of characters.
    # The "schema" for this file is located within the subscribers zip (and included in this repo).
    # This is an older format, and may not be around forever, but historically it's in all the prior subscriber
    # files.

    # For instance,
    """
    L  AN  12 00001  NONE    RECORD IDENTIFIER  
                             ARTCC IDENTIFIER + ALTITUDE STRUCTURE CODE +  
                             FIVE CHARACTER ARTCC BOUNDARY POINT DESIGNATOR  
    L  AN0040 00013  NONE    CENTER NAME  
    L  AN0010 00053  NONE    ALTITUDE STRUCTURE DECODE NAME  
    L  AN0014 00063  ARP4    LATITUDE OF THE BOUNDARY POINT  
    L  AN0014 00077  ARP5    LONGITUDE OF THE BOUNDARY POINT  
    L  AN0300 00091  ARB21   DESCRIPTION OF BOUNDARY LINE CONNECTING POINTS  
                             ON THE BOUNDARY  
    L  AN0006 00391  ARB28   SIX DIGIT NUMBER USED TO MAINTAIN PROPER SEQUENCE  
                             OF BOUNDARY SEGMENTS FOR REPORT PURPOSES  
    L  AN0001 00397  ARP25   AN 'X' IN THIS FIELD INDICATES THIS POINT IS USED  
                             ONLY IN THE NAS DESCRIPTION AND NOT THE LEGAL  
                             DESCRIPTION  
    """

    # So the center's name is 40 characters long, starts at the 13th character (1-index)

    lines = content.splitlines()
    records = []
    for idx, line in enumerate(lines):
        try:
            data = {}  # dict to store our fields of interest
            center, designators = line[0:12].split(' ')
            altitude = designators.split('*')[1]  # *H*, *L*, *F*
            point_number = designators[-5:]
            line_connector_description = line[91 - 1:91 - 1 + 300].strip()
            data['line_idx'] = idx
            data['full_line'] = line
            data['CENTER'] = center
            data['POINT_NUMBER'] = point_number
            data['ALT'] = altitude
            data['LAT'] = line[63 - 1:63 - 1 + 14].strip()
            data['LON'] = line[77 - 1:77 - 1 + 14].strip()
            data['CONNECTOR_DESCRIPTION'] = line_connector_description
            data['SKYVEC_REP'] = convert_skyvec_rep(data['LAT']) + convert_skyvec_rep(data['LON'])
        except Exception as e:
            print "Error reading data from line: ", line
            raise e

        records.append(data)

    print("First three records:")
    pprint.PrettyPrinter().pprint(records[:3])

    # technically, we could do the above in one pass, but sometimes it's better to build out iteratively
    # (since this is a small file processed once, that's probably ok)


    # We want to convert each individual record into an aggregate boundary

    boundaries = []
    current_boundary = {}
    current_boundary['points'] = []
    full_boundary = False  # State variable to track if we're
    start_new_boundary = True
    for data_idx, data_record in enumerate(records):

        # We aren't going to bother with FIR or CTA boundaries. (international and oceanic)
        #if data_record['ALT'] not in ('H', 'L'):
        #    continue

        if full_boundary:
            full_boundary = False
            boundaries.append(current_boundary)
            current_boundary = {}

        if start_new_boundary:
            start_new_boundary = False
            current_boundary['points'] = []
            current_boundary['SKYVEC_REP'] = []
            current_boundary['point_numbers'] = []
            current_boundary['CENTER'] = data_record['CENTER']
            current_boundary['ALT'] = data_record['ALT']
            current_boundary['start_index'] = data_record['POINT_NUMBER']

        # detect if we start a new center, but don't have the "to point of beginning"
        # in the last record
        if ('CENTER' in current_boundary and
                    data_record['CENTER'] != current_boundary['CENTER'] and
                not full_boundary):
            print("Invalid record boundary")
            print("Previous record")
            pprint.PrettyPrinter().pprint(records[data_idx - 1])
            print("Current record")
            pprint.PrettyPrinter().pprint(data_record)
            print("Last recorded boundary")
            pprint.PrettyPrinter().pprint(boundaries[-1])
            print("Current boundary")
            pprint.PrettyPrinter().pprint(current_boundary)
            return

        if 'POINT OF BEGINNING' in data_record['CONNECTOR_DESCRIPTION']:
            full_boundary = True
            start_new_boundary = True
            current_boundary['end_index'] = data_record['POINT_NUMBER']

        try:
            lat, lon = (parse_dms(data_record['LAT']), parse_dms(data_record['LON']))
            current_boundary['points'].append((lon, lat))
            current_boundary['SKYVEC_REP'].append(data_record['SKYVEC_REP'])
            current_boundary['point_numbers'].append(data_record['POINT_NUMBER'])
        except Exception as e:
            print "Unable to parse line at index %s\n%s" % (data_record['line_idx'], data_record['full_line'])
            raise e

    centers = defaultdict(dict)
    for boundary in boundaries:
        boundary['SKYVEC_REP'] = ' '.join(boundary['SKYVEC_REP'])
        polygon = Polygon(boundary['points'])
        boundary['points'] = [x for x in orient(polygon, sign=-1.0).exterior.coords]
        centers[boundary['CENTER']][boundary['ALT']] = boundary

    print "example processed boundary"
    pprint.PrettyPrinter().pprint(boundaries[0])

    matching_altitudes = set()
    unmatched_altitudes = set()
    only_one_altitude = set()

    for center in centers:
        if 'L' in centers[center] and 'H' in centers[center]:
            if centers[center]['L']['SKYVEC_REP'] == centers[center]['H']['SKYVEC_REP']:
                matching_altitudes.add(center)
            else:
                unmatched_altitudes.add(center)
        else:
            only_one_altitude.add(center)

    print 'matching altitudes: ', matching_altitudes
    print 'unmatched altitudes: ', unmatched_altitudes
    print 'only one altitudes: ', only_one_altitude

    all_centers = matching_altitudes.union(unmatched_altitudes).union(only_one_altitude)

    print 'total of %s centers' % (len(all_centers),)

    print '\nonly one center'
    for one_alt in only_one_altitude:
        for a in centers[one_alt]:
            print one_alt, a, centers[one_alt][a]['SKYVEC_REP'], '\n'

    print '\nexample zdc'
    for a in centers['ZDC']:
        print a, centers['ZDC'][a]['SKYVEC_REP'], '\n'

    centers_csv = []
    for boundary in boundaries:
        if boundary['CENTER'] in only_one_altitude:
            continue
        center_csv = {}
        center_csv['Facility'] = center
        center_csv['FavID'] = "_".join([center,
                                        boundary['ALT'],
                                        boundary['start_index'],
                                        boundary['end_index']])
        center_csv['Inclusion'] = '1'
        center_csv['AltLow'] = '18000' if boundary['ALT'] == 'H' else '0'
        center_csv['AltHigh'] = '60000' if boundary['ALT'] == 'H' else '18000'
        points = boundary['points'] + [boundary['points'][0]]
        points = ['[%s, %s]' % (lon, lat) for lon, lat in points]
        points = '[[%s]]' % (','.join(reversed(points)),)
        center_csv['GeoJSON'] = '{"type": "Polygon", "coordinates": %s}' % (points,)
        centers_csv.append(center_csv)

    fieldnames = ['Facility', 'FavID', 'Inclusion', 'AltLow', 'AltHigh', 'GeoJSON']
    with open(args.out_file, 'w') as f:
        writer = csv.DictWriter(f,
                                fieldnames=fieldnames,
                                delimiter='|',
                                doublequote=False,
                                escapechar='\\',
                                quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(centers_csv)

    # because I'm running out of time and can't get the CSV to match the expected format :)
    with open(args.out_file, 'r') as f:
        content = f.read()

    with open(args.out_file, 'w') as f:
        f.write(content.replace("\\", ""))


if __name__ == "__main__":
    main()
