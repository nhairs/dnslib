#!/usr/bin/env python3
"""
    Test dnslib packet encoding/decoding

    Reads test files from dnslib/test (by default) containing
    dump of DNS exchange (packet dump & parse output) and test
    round-trip parsing - specifically:

        - Parse packet data and zone format data and compare
        - Repack parsed packet data and compare with original

    This should test the 'parse', 'fromZone' and 'pack' methods of the
    associated record types.

    The original parsed output is created using dnslib by default so systematic
    encode/decode errors will not be found. By default the test data is
    checked against 'dig' to ensure that it is correct when generated
    using the --new option.

    By default the module runs in 'unittest' mode (and supports unittest
    --verbose/--failfast options)

    The module can also be run in interactive mode (--interactive) and inspect
    failed tests (--debug)

    New test data files can be automatically created using the:

        --new <domain> <type>

    option. The data is checked against dig output and an error raised if
    this does not match. This is effectively the same as running:

        python -m dnslib.client --query --hex --dig <domain> <type>

    It is possible to manually generate test data files using dnslib.client
    even if the dig data doesn't match (this is usually due to an unsupported
    RDATA type which dnslib will output in hex rather then parsing contents).
    The roundtrip tests will still work in this case (the unknown RDATA is
    handled as an opaque blob).

    In some cases the tests will fail as a result of the zone file parser
    being more fragile than the packet parser (especially with broken data)

    Note - unittests are dynamically generated from the test directory contents
    (matched against the --glob parameter)

"""


import argparse
import code
import glob
import os
import os.path
import sys
import unittest
from subprocess import getoutput

from dnslib.dns import DNSRecord, EDNS0
from dnslib.digparser import DigParser


class TestContainer(unittest.TestCase):
    pass


def new_test(domain, qtype, address="8.8.8.8", port=53, nodig=False, dnssec=False):
    tcp = False
    q = DNSRecord.question(domain, qtype)
    if dnssec:
        q.add_ar(EDNS0(flags="do", udp_len=4096))
        q.header.ad = 1
    a_pkt = q.send(address, port)
    a = DNSRecord.parse(a_pkt)
    if a.header.tc:
        tcp = True
        a_pkt = q.send(address, port, tcp)
        a = DNSRecord.parse(a_pkt)

    if not nodig:
        dig_opts = "+dnssec" if dnssec else "+noedns +noadflag"
        dig = getoutput(f"dig +qr {dig_opts} -p {port} {domain} {qtype} @{address}")
        dig_reply = list(iter(DigParser(dig)))
        # DiG might have retried in TCP mode so get last q/a
        q_dig = dig_reply[-2]
        a_dig = dig_reply[-1]

        if q != q_dig or a != a_dig:
            if q != q_dig:
                print(";;; ERROR: Diff Question differs")
                for d1, d2 in q.diff(q_dig):
                    if d1:
                        print(f";; - {d1}")
                    if d2:
                        print(f";; + {d2}")
            if a != a_dig:
                print(";;; ERROR: Diff Response differs")
                for d1, d2 in a.diff(a_dig):
                    if d1:
                        print(f";; - {d1}")
                    if d2:
                        print(f";; + {d2}")
            return

    if dnssec:
        fname = f"{domain}-{qtype}-dnssec"
    else:
        fname = f"{domain}-{qtype}"
    print(f"Writing test file: {fname}")
    with open(fname, "w") as f:
        print(";; Sending:", file=f)
        print(";; QUERY:", q.pack().hex(), file=f)
        print(q, file=f)
        print(file=f)
        print(";; Got answer:", file=f)
        print(";; RESPONSE:", a_pkt.hex(), file=f)
        print(a, file=f)
        print(file=f)


def check_decode(f, debug=False):
    errors = []

    # Parse the q/a records
    with open(f) as x:
        q, r = DigParser(x)

    # Grab the hex data
    with open(f, "rt") as digfile:
        for line in digfile:
            if line.startswith(";; QUERY:"):
                qdata = bytes.fromhex(line.split()[-1])
            elif line.startswith(";; RESPONSE:"):
                rdata = bytes.fromhex(line.split()[-1])

    # Parse the hex data
    qparse = DNSRecord.parse(qdata)
    rparse = DNSRecord.parse(rdata)

    # Check records generated from DiG input matches
    # records parsed from packet data
    if q != qparse:
        errors.append(("Question", q.diff(qparse)))
    if r != rparse:
        errors.append(("Reply", r.diff(rparse)))

    # Repack the data
    qpack = qparse.pack()
    rpack = rparse.pack()

    # Check if repacked question data matches original
    # We occasionally get issues where original packet did not
    # compress all labels - in this case we reparse packed
    # record, repack this and compare with the packed data
    if qpack != qdata:
        if len(qpack) < len(qdata):
            # Shorter - possibly compression difference
            if DNSRecord.parse(qpack).pack() != qpack:
                errors.append(("Question Pack", (qdata, qpack)))
        else:
            errors.append(("Question Pack", (qdata, qpack)))
    if rpack != rdata:
        if len(rpack) < len(rdata):
            if DNSRecord.parse(rpack).pack() != rpack:
                errors.append(("Reply Pack", (rdata, rpack)))
        else:
            errors.append(("Reply Pack", (rdata, rpack)))

    if debug:
        if errors:
            print("ERROR\n")
            print_errors(errors)
            print()
            if input(">>> Inspect [y/n]? ").lower().startswith("y"):
                code.interact(local=locals())
            print()
        else:
            print("OK")

    return errors


def print_errors(errors):
    for err, err_data in errors:
        if err == "Question":
            print("Question error:")
            for d1, d2 in err_data:
                if d1:
                    print(f";; - {d1}")
                if d2:
                    print(f";; + {d2}")
        elif err == "Reply":
            print("Reply error:")
            for d1, d2 in err_data:
                if d1:
                    print(f";; - {d1}")
                if d2:
                    print(f";; + {d2}")
        elif err == "Question Pack":
            print("Question pack error")
            print("QDATA:", err_data[0].hex())
            print(DNSRecord.parse(err_data[0]))
            print("QPACK:", err_data[1].hex())
            print(DNSRecord.parse(err_data[1]))
        elif err == "Reply Pack":
            print("Response pack error")
            print("RDATA:", err_data[0].hex())
            print(DNSRecord.parse(err_data[0]))
            print("RPACK:", err_data[1].hex())
            print(DNSRecord.parse(err_data[1]))


def test_generator(f):
    def test(self):
        self.assertEqual(check_decode(f), [])

    return test


if __name__ == "__main__":
    testdir = os.path.join(os.path.dirname(__file__), "test")

    p = argparse.ArgumentParser(description="Test Decode")
    p.add_argument(
        "--new",
        "-n",
        nargs=2,
        metavar="<domain/type>",
        help="Create new test case (args: <domain> <type>)",
    )
    p.add_argument(
        "--dnssec", action="store_true", default=False, help="With --new send DNSSEC request (DO)"
    )
    p.add_argument(
        "--nodig", action="store_true", default=False, help="Don't test new data against DiG"
    )
    p.add_argument("--unittest", action="store_true", default=True, help="Run unit tests")
    p.add_argument("--verbose", action="store_true", default=False, help="Verbose unit test output")
    p.add_argument(
        "--failfast", action="store_true", default=False, help="Stop unit tests on first failure"
    )
    p.add_argument(
        "--interactive", action="store_true", default=False, help="Run in interactive mode"
    )
    p.add_argument(
        "--debug", action="store_true", default=False, help="Debug errors (interactive mode)"
    )
    p.add_argument("--glob", "-g", default="*", help="Glob pattern")
    p.add_argument("--testdir", "-t", default=testdir, help="Test dir (%s)" % testdir)
    p.add_argument("--testfile", "-f", default=None, help="Test single file")
    args = p.parse_args()

    if args.testfile:
        e = check_decode(args.testfile, args.debug)
        if not args.debug:
            if e:
                print("ERROR\n")
                print_errors(e)
                print()
            else:
                print("OK")
    else:
        os.chdir(args.testdir)
        if args.new:
            new_test(args.new[0], args.new[1], nodig=args.nodig, dnssec=args.dnssec)
        elif args.interactive:
            for f in glob.iglob(args.glob):
                if os.path.isfile(f):
                    print(f"-- {f}: ", end="")
                    e = check_decode(f, args.debug)
                    if not args.debug:
                        if e:
                            print("ERROR\n")
                            print_errors(e)
                            print()
                        else:
                            print("OK")
        elif args.unittest:
            for f in glob.iglob(args.glob):
                if os.path.isfile(f):
                    test_name = f"test_{f}"
                    test = test_generator(f)
                    setattr(TestContainer, test_name, test)
            unittest.main(
                argv=[__name__], verbosity=2 if args.verbose else 1, failfast=args.failfast
            )
