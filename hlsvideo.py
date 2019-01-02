# -*- coding: UTF-8 -*-
# @author AoBeom
# @create date 2017-12-25 04:49:59
# @modify date 2018-06-29 17:10:33
# @desc [HLS downloader]
import argparse
import binascii
import logging
import multiprocessing
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from multiprocessing.dummy import Pool

import requests

try:
    import termios
except ImportError:
    pass

if sys.version > '3':
    py3 = True
    import queue
else:
    py3 = False
    import Queue as queue


class HLSVideo(object):
    def __init__(self, debug, proxies):
        self.keyparts = 0
        self.iv = 0
        self.keyfile = None
        self.datename = time.strftime(
            '%y%m%d%H%M%S', time.localtime(time.time()))
        self.debug = debug
        self.dec = 0
        self.type = ""
        self.workdir = os.path.dirname(os.path.abspath(__file__))
        if proxies:
            proxyinfo = {"http": "http://" + proxies,
                         "https": "https://" + proxies}
            self.proxies = proxyinfo
        else:
            self.proxies = None

        self.logs = self.__mylog

    def __mylog(self, mode, *para):
        logging.basicConfig(
            level=logging.NOTSET, format='%(asctime)s - %(filename)s [%(levelname)s] %(message)s')
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        log = getattr(logging, mode)
        msg = ""
        for i in para:
            msg += str(i) + " - "
        log(msg[:-3])

    # requests错误处理
    def __reqerror(self, tryError):
        msg = "ERROR: {}".format(tryError)
        if self.__isWindows():
            interrupt("windows", msg)
        else:
            interrupt("linux", msg)

    # requests处理
    def __requests(self, url, headers=None, cookies=None, timeout=30):
        if headers:
            headers = headers
        else:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.89 Safari/537.36"
            }
        if cookies:
            if self.proxies:
                try:
                    response = requests.get(
                        url, headers=headers, cookies=cookies, timeout=timeout, proxies=self.proxies)
                except BaseException as e:
                    self.__mylog("error", e)
            else:
                try:
                    response = requests.get(
                        url, headers=headers, cookies=cookies, timeout=timeout)
                except BaseException as e:
                    self.__mylog("error", e)
        else:
            if self.proxies:
                try:
                    response = requests.get(
                        url, headers=headers, timeout=timeout, proxies=self.proxies)
                except BaseException as e:
                    self.__mylog("error", e)
            else:
                try:
                    response = requests.get(
                        url, headers=headers, timeout=timeout)
                except BaseException as e:
                    self.__mylog("error", e)
        return response

    # 检查外部应用程序
    def __execCheck(self, video_type):
        prog_openssl = subprocess.Popen(
            "openssl version", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        result_err = prog_openssl.stderr.read()
        if result_err:
            msg = "openssl NOT FOUND."
            if self.__isWindows():
                interrupt("windows", msg)
            else:
                interrupt("linux", msg)
        if video_type == "TVer":
            prog_ffmpeg = subprocess.Popen(
                "ffmpeg -version", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            result = prog_ffmpeg.stderr.read()
            if result:
                msg = "FFMPEG NOT FOUND."
                if self.__isWindows():
                    interrupt("windows", msg)
                else:
                    interrupt("linux", msg)

    # 检查是否地址合法性
    def __checkHost(self, types, url):
        if url.startswith("http"):
            hostdir = ""
        else:
            if py3:
                hostdir = input("Enter %s: " % types)
            else:
                hostdir = raw_input("Enter %s: " % types)
            if hostdir.endswith("/"):
                hostdir = hostdir
            else:
                hostdir = hostdir + "/"
        return hostdir

    # 以当前时间创建文件夹
    def __isFolder(self, filename):
        try:
            filename = filename + "_" + self.datename
            propath = self.workdir
            video_path = os.path.join(propath, filename)
            if not os.path.exists(video_path):
                os.mkdir(video_path)
                return video_path
            else:
                return video_path
        except BaseException as e:
            raise e

    # 判断操作系统
    def __isWindows(self):
        return 'Windows' in platform.system()

    # 识别HLS的类型
    def hlsSite(self, playlist):
        type_dict = {
            "GYAO": "gyao",
            "TVer": "manifest.prod.boltdns.net",
            "Asahi": "tv-asahi",
            "STchannel": "aka-bitis-hls-vod.uliza.jp",
            "FOD": "fod",
            "MBS": "secure.brightcove.com",
            "FUJI": "fujitv.co.jp",
            "ABEMA": "vod-abematv"
        }
        # 通过关键字判断HLS的类型
        siteRule = r'http[s]?://[\S]+'
        check = re.search(siteRule, playlist)
        if check:
            type_check = self.__requests(playlist).text
            for site, keyword in type_dict.items():
                if keyword in playlist:
                    video_type = site
                    break
                if keyword in type_check:
                    video_type = site
                    break
            else:
                video_type = None
            self.type = video_type
            self.__execCheck(video_type)
            if self.debug:
                self.__mylog("debug", video_type, playlist)
            return playlist, video_type
        else:
            msg = "Url is invalid"
            if self.__isWindows():
                interrupt("windows", msg)
            else:
                interrupt("linux", msg)

    # 根据类型做不同的处理 下载key并提取video列表
    def hlsInfo(self, site):
        playlist = site[0]
        video_type = site[1]
        if video_type == "ABEMA":
            spec_info = """Please debug: source -> theoplayer.d.js -> var t = e.data\r\nConsole: Array.from(e.data.St, function(byte){return ('0' + (byte & 0xFF).toString(16)).slice(-2);}).join('')"""
            print(spec_info)
        key_video = []
        # key的下载需要playlist的cookies
        response = self.__requests(playlist)
        m3u8_list_content = response.text
        cookies = response.cookies
        # 提取m3u8列表的最高分辨率的文件
        rule_m3u8 = r"^[\w\-\.\/\:\?\&\=\%\,\+]+"
        rule_bd = r"BANDWIDTH=([\w]+)"
        if video_type == "GYAO":
            rule_bd = r"EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=([\w]+)"
        # 根据码率匹配
        if "m3u8" in m3u8_list_content:
            m3u8urls = re.findall(rule_m3u8, m3u8_list_content, re.S | re.M)
            bandwidth = re.findall(rule_bd, m3u8_list_content, re.S | re.M)
            bandwidth = [int(b) for b in bandwidth]
            group = zip(m3u8urls, bandwidth)
            maxband = max(group, key=lambda x: x[1])
            m3u8kurl = maxband[0]
            if self.debug:
                self.__mylog("debug", "m3u8url", m3u8kurl)
        else:
            msg = "url_error: " + playlist
            self.__reqerror(msg)

        # clip
        if video_type in ["GYAO", "MBS"]:
            self.keyparts = 10

        # m3u8 host
        if video_type == "GYAO":
            m3u8host = "https://" + playlist.split("/")[2] + "/"
        elif video_type == "ABEMA":
            hostlist = playlist.split("/")[1:-1]
            m3u8host = playlist.split("/")[0] + "//"
            for parts in hostlist:
                if parts:
                    m3u8host = m3u8host + parts + "/"
        else:
            m3u8host = self.__checkHost("m3u8 host", m3u8kurl)

        if self.debug:
            self.__mylog("debug", "m3u8", m3u8host)

        m3u8main = m3u8host + m3u8kurl
        m3u8_content = self.__requests(m3u8main).text

        # video host
        rule_video = r'[^#\S+][\w\/\-\.\:\?\&\=\,\+\%]+'
        videourl = re.findall(rule_video, m3u8_content, re.S | re.M)
        videourl_check = videourl[0].strip()

        if video_type in ["GYAO", "FOD"]:
            videohost = m3u8host
        elif video_type in ["Asahi", "STchannel"]:
            hostlist = m3u8main.split("/")[1:-1]
            videohost = m3u8main.split("/")[0] + "//"
            for parts in hostlist:
                if parts:
                    videohost = videohost + parts + "/"
        else:
            videohost = self.__checkHost("video host", videourl_check)

        if self.debug:
            self.__mylog("debug", "videohost", videohost)

        # TVer audio rule [ Only need audio links ]
        if video_type == "TVer":
            audio_rule = r'TYPE=AUDIO(.*?)URI=\"(.*?)\"'
            audio_m3u8_url = re.findall(audio_rule, m3u8_list_content)[-1][-1]
            audio_content = self.__requests(audio_m3u8_url).text
            audiourl = re.findall(rule_video, audio_content, re.S | re.M)
            rule_iv = r'IV=[\w]+'
            iv_value = re.findall(rule_iv, m3u8_content)
            self.iv = ''.join(iv_value).split("=")[-1][2:]
            audiohost = ""

        if video_type == "ABEMA":
            rule_iv = r'IV=[\w]+'
            iv_value = re.findall(rule_iv, m3u8_content)
            self.iv = ''.join(iv_value).split("=")[-1][2:]

        # download key and save url
        rule_key = r'URI=\"(.*?)\"'
        keyurl = re.findall(rule_key, m3u8_content)
        if self.debug:
            self.__mylog("debug", "keyurl", keyurl)

        if keyurl:
            keylist = []
            # tv-asahi分片数由m3u8文件决定
            if video_type == "ABEMA":
                if py3:
                    keyfile = input("Enter Hex Key: ")
                else:
                    keyfile = raw_input("Enter Hex Key: ")
                self.__mylog("info", "(1)Format Key")
                self.keyfile = keyfile
                keylist = [keyfile]
            else:
                keyfolder = self.__isFolder("keys")
                if "tv-asahi" in m3u8main:
                    if len(keyurl) > 1:
                        key_parts = keyurl[1].split("/")[-1].split("=")[-1]
                        self.keyparts = int(key_parts)
                if self.debug:
                    self.__mylog("debug", "videoparts", self.keyparts)
                if self.debug:
                    self.__mylog("debug", "keyfolder", keyfolder)
                t = len(keyurl)
                self.__mylog("info", "(1)GET Key", t)
                for i, k in enumerate(keyurl):
                    # download key
                    key_num = i + 1
                    url = m3u8host + k
                    if video_type == "FOD":
                        url = k
                    # rename key
                    keyname = str(key_num).zfill(4) + "_key"
                    keypath = os.path.join(keyfolder, keyname)
                    keylist.append(keypath)
                    r = self.__requests(url, cookies=cookies)
                    with open(keypath, "wb") as code:
                        for chunk in r.iter_content(chunk_size=1024):
                            code.write(chunk)
                if os.path.getsize(keypath) != 16:
                    self.__mylog("error", "key_error", keypath)
            key_video.append(keylist)
            # save urls
            videourls = [videohost + v.strip() for v in videourl]
            if self.debug:
                self.__mylog("debug", "videourls", videourls[0])
            key_video.append(videourls)
            # TVer audio url
            if video_type == "TVer":
                key_audio = []
                audiourls = [audiohost + a.strip() for a in audiourl]
                key_audio.append(keylist)
                key_audio.append(audiourls)
                try:
                    self.__tverdl(key_audio)
                except Exception as e:
                    raise e
        else:
            self.__mylog("info", "(1)No key", "")
            keypath = ""
            videourls = []
            rule_video = r'[^#\S+][\w\/\-\.\:\?\&\=]+'
            # save urls
            videourl = re.findall(rule_video, m3u8_content, re.S | re.M)
            videourl_check = videourl[0].strip()
            videohost = self.__checkHost("video host", videourl_check)
            videourls = [videohost + v.strip() for v in videourl]
            if self.debug:
                self.__mylog("debug", "videourls", videourls[0])
            key_video.append(keypath)
            key_video.append(videourls)
        return key_video

    # 下载重试函数
    def __retry(self, urls, files):
        try:
            self.__mylog("info", "Retrying...", "")
            r = self.__requests(urls)
            with open(files, "wb") as code:
                for chunk in r.iter_content(chunk_size=1024):
                    code.write(chunk)
        except BaseException:
            msg = "[%s] is failed." % urls
            if self.__isWindows():
                interrupt("windows", msg)
            else:
                interrupt("linux", msg)

    # 下载处理函数
    def __download(self, para):
        urls = para[0]
        files = para[1]
        try:
            r = self.__requests(urls)
            with open(files, "wb") as code:
                for chunk in r.iter_content(chunk_size=1024):
                    code.write(chunk)
        except BaseException:
            self.__retry(urls, files)

    # 下载函数
    def hlsDL(self, key_video):
        key_video = key_video
        # Check the number of keys
        key_path = [''.join(kv) for kv in key_video[0]]
        key_num = len(key_path)
        video_urls = key_video[1]
        videos = []  # 视频保存路径列表
        video_folder = self.__isFolder("encrypt")
        if self.debug:
            self.__mylog("debug", "encfolder", video_folder)
        # Rename the video for sorting
        for i in range(0, len(video_urls)):
            video_num = i + 1
            video_name = str(video_num).zfill(4) + ".ts"
            video_encrypt = os.path.join(video_folder, video_name)
            videos.append(video_encrypt)
        total = len(video_urls)
        self.__mylog("info", "(2)GET Videos", total)
        self.__mylog("info", "--- Downloading ---")
        thread = int(total / 4)
        # Multi-threaded configuration
        if thread > 100:
            thread = 20
        else:
            thread = 10
        # 多线程无进度条
        # pool = Pool(thread)
        # pool.map(self.__download, zip(video_urls, videos))
        # pool.close()
        # pool.join()

        # 多线程进度条版本
        t = threadProcBar(self.__download, list(
            zip(video_urls, videos)), thread)
        t.worker()
        t.process()

        present = len(os.listdir(video_folder))
        # 比较总量和实际下载数
        if present != total:
            self.__mylog("error", "total_error", present + "/" + total)
        # 有key则调用解密函数
        if key_path:
            # 只有1个key调用hlsDec
            if key_num == 1:
                key_path = ''.join(key_path)
                try:
                    self.__mylog("info", "(3)Decrypting...")
                    self.hlsDec(key_path, videos)
                except Exception as e:
                    raise e
            # hlsPartition
            else:
                try:
                    self.__mylog("info", "(3)Decrypting...")
                    self.hlsPartition(key_path, videos)
                except Exception as e:
                    raise e
        # 无key则直接合并视频
        else:
            try:
                self.__mylog("info", "(3)Decrypting...")
                self.hlsConcat(videos)
            except Exception as e:
                raise e

        # 后置处理 删除临时文件
        folder = "decrypt_" + self.datename
        video_name = os.path.join(folder, self.datename + ".ts")
        if os.path.exists(video_name):
            self.__mylog("info", "(4)Clean up tmp files...")
            if self.debug:
                msg = "Please check [ {}/{}.ts ]".format(folder, self.datename)
            else:
                msg = "Please check [ {}.ts ]".format(self.datename)
            # 清理临时文件
            if not self.debug:
                enpath = "encrypt_" + self.datename
                kpath = "keys_" + self.datename
                os.chmod(folder, 128)
                os.chmod(enpath, 128)
                if os.path.exists(kpath):
                    os.chmod(kpath, 128)
                    shutil.rmtree(kpath)
                shutil.rmtree(enpath)
                shutil.copy(video_name, self.workdir)
                shutil.rmtree(folder)
                if self.type == "TVer":
                    self.__concat_audio_video()
                    msg = "Please Check [ %s_all.ts ]" % self.datename
            if self.__isWindows():
                interrupt("windows", msg)
            else:
                interrupt("linux", msg)
        else:
            self.__mylog("error", "not_found", self.datename)

    # 视频解密函数
    def hlsDec(self, keypath, videos, outname=None, ivs=None, videoin=None):
        if outname is None:
            outname = self.datename + ".ts"
        else:
            outname = outname
        videos = videos
        indexs = range(0, len(videos))
        # 判断iv值，为空则序列化视频下标，否则用给定的iv值
        if ivs is None:
            ivs = range(1, len(videos) + 1)
        else:
            ivs = ivs
        if self.keyfile:
            KEY = self.keyfile
        else:
            k = keypath
            # format key
            STkey = open(k, "rb").read()
            KEY = binascii.b2a_hex(STkey)
        if py3 and self.keyfile is None:
            KEY = str(KEY, encoding="utf-8")
        if videoin:
            videoin = videoin
        else:
            videoin = self.__isFolder("encrypt")
        videoout = self.__isFolder("decrypt")
        if self.debug is True and self.dec == 0:
            self.dec = 1
            self.__mylog("debug", "decfolder", videoout)
        new_videos = []
        # Decrypt the video
        for index in indexs:
            inputV = videos[index]
            iv = ivs[index]
            if self.__isWindows():
                outputV = videos[index].split("\\")[-1] + "_dec.ts"
            else:
                outputV = videos[index].split("/")[-1] + "_dec.ts"
            # format iv
            if self.iv != 0:
                iv = self.iv
            else:
                iv = '%032x' % iv
            inputVS = os.path.join(videoin, inputV)
            outputVS = os.path.join(videoout, outputV)
            # 解密命令 核心命令
            command = "openssl aes-128-cbc -d -in {input} -out {output} -nosalt -iv {iv} -K {key}".format(
                input=inputVS, output=outputVS, iv=iv, key=KEY)
            p = subprocess.Popen(command, stderr=subprocess.PIPE, shell=True)
            result = p.stderr.read()
            if result:
                if self.debug:
                    self.__mylog("info", "video", inputV)
                    self.__mylog("info", "IV", iv)
                    self.__mylog("info", "KEY", KEY)
                    self.__mylog("debug", "deccmd", command)
                self.__mylog("error", "dec_error", videoin)
            new_videos.append(outputVS)
        self.hlsConcat(new_videos, outname)

    # 合并处理函数
    def __concat(self, ostype, inputv, outputv):
        if ostype == "windows":
            os.system("copy /B " + inputv + " " + outputv + " >nul 2>nul")
        elif ostype == "linux":
            os.system("cat " + inputv + " >" + outputv)

    # windows特殊处理
    def __longcmd(self, videolist, videofolder, videoput):
        videolist = videolist
        totle = len(videolist)
        # 将cmd的命令切割
        cut = 50
        part = totle / cut
        parts = []
        temp = []
        for v in videolist:
            temp.append(v)
            if len(temp) == cut:
                parts.append(temp)
                temp = []
            if len(parts) == part:
                parts.append(temp)
        outputs = []
        for index, p in enumerate(parts):
            stream = ""
            outputname = "out_" + str(index + 1) + ".ts"
            outputpath = os.path.join(videofolder, outputname)
            outputs.append(outputpath)
            for i in p:
                stream += i + "+"
            videoin = stream[:-1]
            self.__concat("windows", videoin, outputpath)
        flag = ""
        for output in outputs:
            flag += output + "+"
        videoin_last = flag[:-1]
        self.__concat("windows", videoin_last, videoput)

    # 视频合并函数
    def hlsConcat(self, videolist, outname=None):
        if outname is None:
            outname = self.datename + ".ts"
        else:
            outname = outname
        videolist = videolist
        stream = ""
        # 解密视频路径
        video_folder = self.__isFolder("decrypt")
        videoput = os.path.join(video_folder, outname)
        # Windows的合并命令
        if self.__isWindows():
            if len(videolist) > 50:
                self.__longcmd(videolist, video_folder, videoput)
            else:
                for v in videolist:
                    stream += v + "+"
                videoin = stream[:-1]
                self.__concat("windows", videoin, videoput)
        # Liunx的合并命令
        else:
            for v in videolist:
                stream += v + " "
            videoin = stream[:-1]
            self.__concat("linux", videoin, videoput)

    # 多key解密函数
    def hlsPartition(self, keypath, videos):
        keypath = keypath
        videos = videos
        key_num = len(keypath)
        video_num = len(videos)
        if self.keyparts > 0:
            parts_s = int(self.keyparts)
        else:
            # 根据视频数和key数分片
            parts_s = int(round((video_num) / float(key_num)))
        # ditc[key]=list[videos] 一个key对应多个video
        for i in range(0, key_num):
            out_num = i + 1
            key = keypath[i]
            outname = "video_" + str(out_num).zfill(4) + ".ts"
            index_s = i * parts_s
            index_e = index_s + parts_s
            ivs = range(index_s + 1, index_e + 1)
            video_mvs = videos[index_s:index_e]
            self.hlsDec(key, video_mvs, outname, ivs)
            time.sleep(0.1)
        folder = "decrypt_" + self.datename
        decvideos = os.listdir(folder)
        devs = [decv for decv in decvideos if decv.startswith("video_")]
        devs_path = [os.path.join(self.workdir, folder, dp) for dp in devs]
        try:
            self.hlsConcat(devs_path)
        except Exception as e:
            raise e

    # TVer audio 基本上和hlsDL一致
    def __tverdl(self, keyaudio):
        keyaudio = keyaudio
        keypath = keyaudio[0]
        audiourls = keyaudio[1]
        audio_folder = self.__isFolder("encrypt_audio")
        audios = []
        # Rename the video for sorting
        for i in range(0, len(audiourls)):
            audio_num = i + 1
            audio_name = str(audio_num).zfill(4) + ".ts"
            audio_encrypt = os.path.join(audio_folder, audio_name)
            audios.append(audio_encrypt)
        total = len(audiourls)
        self.__mylog("info", "(SP1)GET Audios", total)
        self.__mylog("info", "--- Downloading ---")
        thread = int(total / 2)
        if thread > 100:
            thread = 100
        else:
            thread = thread
        # pool = Pool(thread)
        # pool.map(self.__download, zip(audiourls, audios))
        # pool.close()
        # pool.join()
        t = threadProcBar(self.__download, list(
            zip(audiourls, audios)), thread)
        t.worker()
        t.process()
        present = len(os.listdir(audio_folder))
        if present != total:
            self.__mylog("error", "total_error", present + "/" + total)
        # Audio merge
        audio_file = self.datename + "_audio.ts"
        if keypath:
            keypath = ''.join(keypath)
            self.hlsDec(keypath, audios, audio_file)
        folder_audio = "decrypt_" + self.datename
        audioname = os.path.join(folder_audio, audio_file)
        if os.path.exists(folder_audio):
            self.__mylog("info", "(SP1)Audio Complete")
        if not self.debug:
            enpath = "encrypt_audio_" + self.datename
            os.chmod(folder_audio, 128)
            os.chmod(enpath, 128)
            shutil.rmtree(enpath)
            shutil.copy(audioname, self.workdir)
            shutil.rmtree(folder_audio)

    # TVer video/audio merge
    def __concat_audio_video(self):
        if self.iv != 0:
            # TVer音视频合并
            v = os.path.join(self.workdir, self.datename + ".ts")
            a = os.path.join(self.workdir, self.datename + "_audio.ts")
            try:
                os.system("ffmpeg -i " + v + " -i " + a +
                          " -c copy " + self.datename + "_all.ts")
            except BaseException:
                msg = "FFMPEG ERROR."
                if self.__isWindows():
                    interrupt("windows", msg)
                else:
                    interrupt("linux", msg)


# 多线程进度条
class threadProcBar(object):
    def __init__(self, func, tasks, pool=multiprocessing.cpu_count()):
        self.func = func
        self.tasks = tasks

        self.bar_i = 0
        self.bar_len = 50
        self.bar_max = len(tasks)

        self.p = Pool(pool)
        self.q = queue.Queue()

    def __dosth(self, percent, task):
        if percent == self.bar_max:
            return self.done
        else:
            self.func(task)
            return percent

    def worker(self):
        pool = self.p
        for i, task in enumerate(self.tasks):
            try:
                percent = pool.apply_async(self.__dosth, args=(i, task))
                self.q.put(percent)
            except BaseException:
                break

    def process(self):
        pool = self.p
        while 1:
            result = self.q.get().get()
            if result == self.bar_max:
                self.bar_i = self.bar_max
            else:
                self.bar_i += 1
            num_arrow = int(self.bar_i * self.bar_len / self.bar_max)
            num_line = self.bar_len - num_arrow
            percent = self.bar_i * 100.0 / self.bar_max
            process_bar = '[' + '>' * num_arrow + '-' * \
                num_line + ']' + '%.2f' % percent + '%' + '\r'
            sys.stdout.write(process_bar)
            sys.stdout.flush()
            if result == self.bar_max-1:
                pool.terminate()
                break
        pool.join()
        self.__close()

    def __close(self):
        print('')


def interrupt(ostype, msg):
    if ostype == "windows":
        sys.stdout.write(msg + "\r\n")
        sys.stdout.flush()
        os.system("echo Press any key to Exit...")
        os.system("pause > nul")
    if ostype == "linux":
        fd = sys.stdin.fileno()
        old_ttyinfo = termios.tcgetattr(fd)
        new_ttyinfo = old_ttyinfo[:]
        new_ttyinfo[3] &= ~termios.ICANON
        new_ttyinfo[3] &= ~termios.ECHO
        sys.stdout.write(msg + "\r\n" + "Press any key to Exit..." + "\r\n")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSANOW, new_ttyinfo)
        os.read(fd, 7)
        termios.tcsetattr(fd, termios.TCSANOW, old_ttyinfo)
    sys.exit()


def opts():
    paras = argparse.ArgumentParser(description="Download HLS video")
    paras.add_argument('-d', dest='debug', action="store_true",
                       default=False, help="DEBUG")
    paras.add_argument('-k', dest='key', action="store",
                       default=None, help="Key")
    paras.add_argument('-p', dest='proxy', action="store",
                       default=None, type=str, help="proxy")
    args = paras.parse_args()
    return args


def main():
    para = opts()
    debug = para.debug
    proxies = para.proxy

    if py3:
        playlist = input("Enter Playlist URL: ")
    else:
        playlist = raw_input("Enter Playlist URL: ")
    if playlist:
        HLS = HLSVideo(debug=debug, proxies=proxies)
        site = HLS.hlsSite(playlist)
        keyvideo = HLS.hlsInfo(site)
        HLS.hlsDL(keyvideo)
    else:
        msg = "url invalid."
        if 'Windows' in platform.system():
            interrupt("windows", msg)
        else:
            interrupt("linux", msg)


if __name__ == "__main__":
    main()
