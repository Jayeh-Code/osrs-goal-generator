Live boss totals now flow from explicit game kill-count messages into the desktop and accepted boss goals. Duplicate messages do not add kills, player chat is excluded, account changes clear observations, and lower counts cannot reduce HiScores totals. Unsupported messages retain HiScores fallback. Accepted goal checkpoints persist; ordinary observed boss totals are session-local and are reacquired from the next supported message after restarting RuneLite.

Requires companion 0.2.0-beta.2: close the development client and reopen Start RuneLite Dev.cmd. Close the desktop and extract the whole Beta 7 ZIP. Existing saves are reused. The pending Plugin Hub submission remains unchanged.

175 desktop tests and 14 Java tests pass, including duplicate/spoofed messages, account changes, explicit totals, and automatic goal completion. A real in-game kill remains to be verified. Enable the game's kill-count messages; loot alone does not count.
