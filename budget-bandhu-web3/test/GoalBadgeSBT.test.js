const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("GoalBadgeSBT", function () {
  let sbt, owner, verifier, user1, user2;

  beforeEach(async () => {
    [owner, verifier, user1, user2] = await ethers.getSigners();
    const GoalBadgeSBT = await ethers.getContractFactory("GoalBadgeSBT");
    sbt = await GoalBadgeSBT.deploy();
  });

  // ── Deployment ────────────────────────────────────────────────────────
  describe("Deployment", () => {
    it("should set owner correctly", async () => {
      expect(await sbt.owner()).to.equal(owner.address);
    });

    it("should start with tokenId = 1", async () => {
      expect(await sbt.nextTokenId()).to.equal(1);
    });
  });

  // ── Verifier role ─────────────────────────────────────────────────────
  describe("Verifier management", () => {
    it("owner can add a verifier", async () => {
      await sbt.setVerifier(verifier.address, true);
      expect(await sbt.verifiers(verifier.address)).to.be.true;
    });

    it("non-owner cannot set verifier", async () => {
      await expect(
        sbt.connect(user1).setVerifier(verifier.address, true)
      ).to.be.reverted;
    });

    it("cannot set zero address as verifier", async () => {
      await expect(
        sbt.setVerifier(ethers.ZeroAddress, true)
      ).to.be.revertedWith("GoalBadgeSBT: zero address");
    });
  });

  // ── Minting ───────────────────────────────────────────────────────────
  describe("mintBadge", () => {
    const uri = "ipfs://QmTestCID";

    it("owner can mint a badge", async () => {
      await expect(sbt.mintBadge(user1.address, "Emergency Fund", uri))
        .to.emit(sbt, "BadgeMinted")
        .withArgs(user1.address, 1, "Emergency Fund");

      expect(await sbt.ownerOf(1)).to.equal(user1.address);
      expect(await sbt.tokenURI(1)).to.equal(uri);
    });

    it("verifier can mint a badge", async () => {
      await sbt.setVerifier(verifier.address, true);
      await sbt.connect(verifier).mintBadge(user1.address, "Goal", uri);
      expect(await sbt.ownerOf(1)).to.equal(user1.address);
    });

    it("non-verifier cannot mint", async () => {
      await expect(
        sbt.connect(user1).mintBadge(user2.address, "Goal", uri)
      ).to.be.revertedWith("GoalBadgeSBT: not owner or verifier");
    });

    it("cannot mint to zero address", async () => {
      await expect(
        sbt.mintBadge(ethers.ZeroAddress, "Goal", uri)
      ).to.be.revertedWith("GoalBadgeSBT: zero recipient");
    });

    it("cannot mint with empty URI", async () => {
      await expect(
        sbt.mintBadge(user1.address, "Goal", "")
      ).to.be.revertedWith("GoalBadgeSBT: empty URI");
    });

    it("tokenId increments correctly", async () => {
      await sbt.mintBadge(user1.address, "Goal1", uri);
      await sbt.mintBadge(user2.address, "Goal2", uri);
      expect(await sbt.ownerOf(1)).to.equal(user1.address);
      expect(await sbt.ownerOf(2)).to.equal(user2.address);
      expect(await sbt.nextTokenId()).to.equal(3);
    });
  });

  // ── Batch Minting ─────────────────────────────────────────────────────
  describe("batchMintBadge", () => {
    const uri = "ipfs://QmGroupBadgeCID";

    it("batch mints to multiple recipients", async () => {
      const recipients = [user1.address, user2.address];
      const tx = await sbt.batchMintBadge(recipients, "Goa Trip", uri);
      await tx.wait();

      expect(await sbt.ownerOf(1)).to.equal(user1.address);
      expect(await sbt.ownerOf(2)).to.equal(user2.address);
    });

    it("reverts on empty list", async () => {
      await expect(
        sbt.batchMintBadge([], "Goal", uri)
      ).to.be.revertedWith("GoalBadgeSBT: empty list");
    });

    it("reverts if batch > 20", async () => {
      const recipients = Array(21).fill(user1.address);
      await expect(
        sbt.batchMintBadge(recipients, "Goal", uri)
      ).to.be.revertedWith("GoalBadgeSBT: max 20 per batch");
    });
  });

  // ── Soulbound enforcement ─────────────────────────────────────────────
  describe("Soulbound (non-transferable)", () => {
    beforeEach(async () => {
      await sbt.mintBadge(user1.address, "Goal", "ipfs://QmTest");
    });

    it("should BLOCK transferFrom", async () => {
      await expect(
        sbt.connect(user1).transferFrom(user1.address, user2.address, 1)
      ).to.be.revertedWith("GoalBadgeSBT: non-transferable");
    });

    it("should BLOCK safeTransferFrom", async () => {
      await expect(
        sbt.connect(user1)["safeTransferFrom(address,address,uint256)"](
          user1.address, user2.address, 1
        )
      ).to.be.revertedWith("GoalBadgeSBT: non-transferable");
    });

    it("owner still holds the token after transfer attempt", async () => {
      try {
        await sbt.connect(user1).transferFrom(user1.address, user2.address, 1);
      } catch {}
      expect(await sbt.ownerOf(1)).to.equal(user1.address);
    });
  });
});
