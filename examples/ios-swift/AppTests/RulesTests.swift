//
//  RulesTests.swift
//
//  Each test names the spec IDs it checks before the first colon.
//  `tools/specloop coverage` maps them back to docs/SPEC.md.
//

import Testing
@testable import App

struct XPRulesTests {
    @Test("XP-1: each tier pays its table reward")
    func tierRewards() {
        #expect(RarityTier.common.xpReward == 10)
        #expect(RarityTier.uncommon.xpReward == 25)
        #expect(RarityTier.rare.xpReward == 60)
        #expect(RarityTier.legendary.xpReward == 150)
    }

    @Test("XP-2, XP-3: relabeling keeps the scanner's XP")
    func relabelKeepsScannerXP() {
        let catchResult = CatchRules.relabel(scanned: .commonBreed, picked: .legendaryBreed)
        #expect(catchResult.xp == RarityTier.common.xpReward)
    }
}

@MainActor
struct LevelRulesTests {
    @Test("LVL-1: level n starts at 50·n·(n−1) XP", arguments: 1...20)
    func levelFloor(level: Int) {
        #expect(PlayerProfile(xp: 50 * level * (level - 1)).level == level)
    }
}
