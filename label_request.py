import requests
import re
import argparse
import threading
import time
import io
from Queue import Queue


lock = threading.Lock()
count = 0


class RequestDataSet:
    def __init__(self, name):
        self.f    = io.open(name, mode="rb")
        self.path = name
        self.line = 0

    def readLine(self, request=None):
        line = self.f.readline()
        self.line += 1

        if request:
            request['raw'] += line

        if len(line) > 1 and line[-2] == '\r' and line[-1] == '\n':
            return line[:-2]

        if len(line) > 0 and line[-1] == '\n':
            return line[:-1]

        return line

    def readRequests(self):
        setRequests = []

        while True:
            request    = {}
            newRequest = self.getNextRequest()
            if newRequest is None:
                break

            request['req']   = newRequest
            request['check'] = 0

            setRequests.append(request)

        self.setRequests   = setRequests
        self.totalRequests = len(self.setRequests)

        print "Total request: %d" % self.totalRequests

    def getNextRequest(self):
        newRequest = {}
        newRequest['raw'] = ''
        line  = self.readLine(newRequest)

        try:
            if line == '':
                return None

            newRequest['protocol'] = re.findall("HTTP.+\S", line)[0]

            if " http" in line:
                newRequest['host']   = re.findall("(?:http|https)://(.+?)(?:/|\s)", line)[0]
            else:
                newRequest['host'] = ''

            url = re.findall(" (.+) ", line)[0]

            if newRequest['host'] == '':
                newRequest['uri'] = url
            else:
                newRequest['uri']   = re.findall("%s(.*)" % newRequest['host'], url)[0]
            
            newRequest['method'] = re.findall("\S+", line)[0]
            newRequest['header'] = {}
            newRequest['data']   = {}

            line = self.readLine(newRequest)

            while line:
                field = line.split(": ")
                if len(field) == 1:
                    field = line.split(":", 1)

                if field[0] == "Host":
                    if newRequest['host'] == '':
                        newRequest['host'] = field[1]
                    field[1] = "%s"

                newRequest['header'][field[0]] = field[1]

                line = self.readLine(newRequest)

            if newRequest['method'] == 'POST' or newRequest['method'] == 'PUT':

                body = self.readLine()
                newRequest['body'] = body
                if body:
                    params = body.split("&")
                    # print len(params)
                    for param in params:
                        pair = param.split("=")
                        try:
                            newRequest['data'][pair[0]] = pair[1]
                        except:
                            print newRequest['raw']

                self.readLine()
            else:
                self.readLine()

        except Exception, e:
            print "Parse request fail on line %s!" % self.line
            print "Error: %s" % str(e)
            return None

        return newRequest

    def show(self, number, host):

        if number is None:
            setRequests = self.setRequests
            i = 1
        elif len(number) == 1:
            setRequests = self.setRequests[:number[0]]
            i = 1
        elif len(number) == 2:
            setRequests = self.setRequests[number[0] - 1 : number[1]]
            i = number[0]
        else:
            print "Wrong set request!"
            return

        totalRequests = self.totalRequests

        try:
            for request in setRequests:
                request = request['req']
                print '\n%s' % request['raw']
                print 'Request %d/%d' % (i, totalRequests)
                if host is not None:
                    check = raw_input('Send this request to %s (y/Enter): ' % host)
                    if check == 'y':
                        URL = "http://" + host + request['uri']
                        request['header']['Host'] = request['header']['Host'] % host

                        r = requests.request(method=request['method'], url=URL,
                        headers=request['header'], data=request['data'], allow_redirects=False)

                        print "\rSucess request!; Status code: %d" % r.status_code
                else:
                    raw_input()

                i = i + 1
            else:
                return

        except KeyboardInterrupt:
            return

    def validateLabelRequest(self, manual, filter_str, RE=False):
        # print filter_str
        if filter_str is not None:
            print filter_str
            for request in self.setRequests:
                if RE is True:
                    if re.search(filter_str, request['req']['raw']):
                        request['check'] = 1
                    else:
                        request['check'] = 0
                else:
                    if filter_str in request['req']['raw']:
                        request['check'] = 1
                    else:
                        request['check'] = 0
            else:
                self.endJob()
                return

        if manual is True:
            i = 1
            try:
                for request in self.setRequests:
                    print '\n%s' % request['req']['raw']
                    print 'Request %d/%d' % (i, self.totalRequests)
                    confirm = raw_input('Does it\'s anomalous(y/Enter): ')

                    if confirm == 'y':
                        request['check'] = 1
                    else:
                        request['check'] = -1

                    i = i + 1
                else:
                    self.endJob()
                    return

            except KeyboardInterrupt:
                self.endJob()
                return

        return

    def doRequest(self, number, host, threadNumber):
        if host is None:
            print "Must specify host"
            return

        if number is None:
            setRequests = self.setRequests
        elif len(number) == 1:
            setRequests = self.setRequests[:number[0]]
        elif len(number) == 2:
            setRequests = self.setRequests[number[0] : number[1]]
        else:
            print "Wrong set request!"
            return

        totalRequests = len(setRequests)

        threads = []
        q = Queue(50)

        for i in range(threadNumber):
            thread = RequestThread(q, totalRequests, host)
            threads.append(thread)

        print "---Starting send request to %s with %d concurrent requests---" % (host, threadNumber)
        startTime = time.time()

        for thread in threads:
            thread.start()

        for request in setRequests:
            q.put(request)
        q.join()

        print
        print "---Ending send request---"
        endTime = time.time()
        print "Total time: %f" % (endTime - startTime)

    def reform(self, label):
        # if label is None:
        #   print "Must specific label"
        #   return

        datas = []
        for request in self.setRequests:
            request = request['req']
            # line = "%s%s" % (request['method'], request['uri'])

            # if 'body' in request:
            #   line += "--START-BODY--%s" % request['body']

            # for field, value in request['header'].iteritems():
            #   line += "--FIELD--%s:%s" % (field, value.replace(" ",""))

            # reform_file.write("%s\n" % (line))
            # data = []
            # data.append(request['method'])
            # data.append(request['uri'])

            # if 'body' in request:
            #     value = request['body']
            # else:
            #     value = "None"
            # data.append("Body: %s" % value)

            # headerFieldNeed = ['Accept-Encoding', 'Accept-Language', 'Content-Length', 'User-Agent',
            # 'Accept', 'Accept-Charset', 'Cookie', 'Content-Type', 'Referer']

            # for field in headerFieldNeed:
            #     if field in request['header']:
            #         value = request['header'][field]
            #     else:
            #         value = "None"

            #     data.append("%s: %s" % (field, value))

            # line = " ".join(data)
            line = "--12345678-A--\n[31/Aug/2018:13:48:30 +0700] W4jkvn8AAQEAAGfwD2MAAAAG 127.0.0.1 51744 127.0.0.1 80\n--12345678-B--\n"
            line += request['raw']
            if 'body' in request:
                line += "--12345678-C--\n" + request['body'] + "\n"
            line += "--12345678-Z--\n"

            if label is not None:
                line += label
            datas.append(line)

        with open("%s.reform" % self.path, "w") as f:
            f.write("\n".join(datas))

    def endJob(self):
        def save(data, name):
            if len(data) > 0:
                f = open("%s.%s" % (self.f.name, name), "a")

                for request in data:
                    f.write(request)

                f.close()

        print "\nEnd boring job...!"
        self.f.close()

        anomalous = []
        normal    = []
        unlabeled = []
        for request in self.setRequests:
            if request['check'] == 1:
                anomalous.append(request['req']['raw'])
            elif request['check'] == -1:
                normal.append(request['req']['raw'])
            else:
                unlabeled.append(request['req']['raw'])

        print "Anomalous: %d; Normal: %d; Unlabeled: %d" % (len(anomalous), len(normal), len(unlabeled))
        save(anomalous, "anomalous")
        save(normal, "normal")
        save(unlabeled, "unlabeled")
        
    def normalize(self):
        # count = {}

        # for request in self.setRequests:
        #   for c in request['req']['raw']:
        #       try:
        #           count[ord(c)] += 1
        #       except KeyError:
        #           count[ord(c)] = 1

        # total = 0
        # a = 0
        # print len(count.keys())
        # for key, value in count.iteritems():
        #   if value == 0:
        #       a += 1
        #       print key,
        #   else:
        #       total += value

        # print a
        # with open(self.name + ".count_chr", "w") as f:
        #   for i in range(self.totalRequests):
        #       f.write(",".join(map(lambda x: x / total, count.values())))
        pass


class RequestThread(threading.Thread):
    def __init__(self, q, total, host=None):
        threading.Thread.__init__(self)
        self.q       = q
        self.host    = host
        self.total   = total
        self.daemon  = True
        
    def run(self):
        global count

        while True:
            req = self.q.get()['req']

            if self.host is None:
                self.host = req['host']

            URL = "http://" + self.host + req['uri']
            req['header']['Host'] = req['header']['Host'] % self.host

            try:
                r = requests.request(method=req['method'], url=URL,
                headers=req['header'], data=req['data'], allow_redirects=False)
                # print 'check'
                # lock.acquire()
                count = count + 1
                print "\rSuccess send request: %d/%d; Method: %s; Status code: %d" % (count, self.total, req['method'], r.status_code)
                # lock.release()
            except Exception, e:
                lock.acquire()
                print "Fail request: %d/%d: %s" % (count, self.total, str(e))
                print "Raw: " + req['raw']
                print "Real: " + URL
                lock.release()
                continue
            
            self.q.task_done()


def main():
    parser = argparse.ArgumentParser('handleRequest')
    parser.add_argument('FILE', help='Log file', type=str)
    subparser = parser.add_subparsers(help="Optional function", dest="choice")

    show = subparser.add_parser('show', help='Show request')
    show.add_argument('-H', '--host', help='Host to send request', type=str)
    show.add_argument('-n', '--number', help='Number requests to show', type=int, nargs="+")

    check = subparser.add_parser('check', help='Send request to host')
    check.add_argument('-H', '--host', help='Host to send request', type=str, required=True)
    check.add_argument('-n', '--number', help='Number requests to check', type=int, nargs="+")
    check.add_argument('-t', '--thread', help='Number threadss to check', type=int, default=4)

    label = subparser.add_parser('label', help='Label set requests')
    label.add_argument('-m', '--manual', help='Manual check request', action="store_true")
    label.add_argument('-f', '--filter_string', dest="string", help='String to filter request', type=str)
    label.add_argument('-e', '--regex', help='Use regex', action="store_true")

    reform = subparser.add_parser('reform', help='Reform log file')
    reform.add_argument('-l' , '--label', help="Label when reform request")

    nor = subparser.add_parser('nor', help='Normalize log file')

    args = parser.parse_args()

    newRequestSet = RequestDataSet(args.FILE)
    newRequestSet.readRequests()

    if args.choice == "show":
        newRequestSet.show(args.number, args.host)
    elif args.choice == "check":
        newRequestSet.doRequest(args.number, args.host, args.thread)
    elif args.choice == "label":
        newRequestSet.validateLabelRequest(args.manual, args.string, args.regex)
    elif args.choice == "reform":
        newRequestSet.reform(args.label)
    elif args.choice == "nor":
        newRequestSet.normalize()
    else:
        print "Must explicit an action!"
    

if __name__ == '__main__':
    main()
