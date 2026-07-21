[app]
title = GuestPlayer
package.name = guestplayer
package.domain = org.test

source.include_exts = py,png,jpg,txt,json
source.include_patterns = pattern1.jpg, pattern2.txt

version = 1.0
orientation = portrait

requirements = python3, kivy==2.3.0, kivymd==1.2.0, requests, pycryptodome, ffpyplayer

android.permissions = INTERNET
android.archs = arm64-v8a
