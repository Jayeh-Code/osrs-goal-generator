# Ardougne task mapping

Upstream master resolved during research to `75b623a6bc14237831fddc10b44765c0910a4eb0` (2026-10-04). Snapshot files were fetched in the same research pass. Build and all 12 Java tests pass. Live label comparison is pending a prototype restart.

Task labels and varp-bit mappings adapted from Zoinkwiz/quest-helper, ArdougneEasy/Medium/Hard/Elite.java. Original BSD two-clause copyright notice is retained in ArdougneTasks.java. VarplayerRequirement confirms a set bit indicates the task is no longer incomplete. Read only via RuneLite Client.getVarpValue; no memory inspection or gameplay actions.

Source: https://github.com/Zoinkwiz/quest-helper/tree/master/src/main/java/com/questhelper/helpers/achievementdiaries/ardougne

42 mappings: 10 easy, 12 medium, 12 hard, 8 elite. Bits omitted by the source are deliberately not treated as tasks. Short labels summarize tasks, not full game instructions. Decoded counts must match the independent game count. Matching counts still require journal verification, especially the two Elite completed tasks.

## Original license

/*
 * Copyright (c) 2021, Obasill <https://github.com/Obasill>
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this
 *    list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
 * ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
 * ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 * LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
 * ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
 * SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
