# UDP-SpeedTest
a way to test wifi speed without a server

I thought it would be cool to send UDP packets to my gateway and see where they got stuck. The .py is all Claude Opus, but I am writing the README, yay.

What's interesting is:
- Windows and Linux seem to get high-quality flow control at send time, so they send at "line rate" (WiFi or wired), making this a good test for your current interface speed
- macOS (BSD) happily sends packets faster than line rate and then some are dropped, and even more than that don't make it

To investigate the macOS issue further, Claude added two things:
1. count actual dropped packets
2. measure the interface stats before/after the test

On my Macbook, here are two examples:
- Ethernet+Thunderbolt Display: sends at 1200mbps, drops reported 0, actual traffic out to LAN about 680mbps
- WiFi 802.11ax: sends at 1000mbps, reports drops about 20% of the time, real traffic about 480mbps

So the Mac doesn't seem to have any flow control for this UDP test, but you can probably trust the network interface to report egress.

For the Windows & Linux machines it is quite useful.
