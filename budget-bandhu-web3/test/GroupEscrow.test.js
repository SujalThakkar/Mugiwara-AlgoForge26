const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("GroupEscrow", function () {
  let escrow, owner, creator, member1, member2, stranger;
  const ONE_POL  = ethers.parseEther("1.0");
  const TWO_POL  = ethers.parseEther("2.0");
  const FIVE_POL = ethers.parseEther("5.0");

  let futureDeadline;

  beforeEach(async () => {
    [owner, creator, member1, member2, stranger] = await ethers.getSigners();
    const GroupEscrow = await ethers.getContractFactory("GroupEscrow");
    escrow = await GroupEscrow.deploy();
    futureDeadline = (await time.latest()) + 7 * 24 * 60 * 60; // 7 days
  });

  // ── createPool ────────────────────────────────────────────────────────
  describe("createPool", () => {
    it("creates pool and emits event", async () => {
      await expect(
        escrow.connect(creator).createPool(FIVE_POL, futureDeadline, 5)
      )
        .to.emit(escrow, "PoolCreated")
        .withArgs(1, creator.address, FIVE_POL, futureDeadline, 5);
    });

    it("increments pool ID", async () => {
      await escrow.connect(creator).createPool(FIVE_POL, futureDeadline, 5);
      await escrow.connect(member1).createPool(TWO_POL, futureDeadline, 3);
      expect(await escrow.nextPoolId()).to.equal(3);
    });

    it("rejects zero target", async () => {
      await expect(
        escrow.createPool(0, futureDeadline, 5)
      ).to.be.revertedWith("Escrow: zero target");
    });

    it("rejects deadline in past", async () => {
      const pastDeadline = (await time.latest()) - 1;
      await expect(
        escrow.createPool(FIVE_POL, pastDeadline, 5)
      ).to.be.revertedWith("Escrow: deadline in past");
    });

    it("rejects maxMembers < 2", async () => {
      await expect(
        escrow.createPool(FIVE_POL, futureDeadline, 1)
      ).to.be.revertedWith("Escrow: members 2-50");
    });

    it("rejects maxMembers > 50", async () => {
      await expect(
        escrow.createPool(FIVE_POL, futureDeadline, 51)
      ).to.be.revertedWith("Escrow: members 2-50");
    });
  });

  // ── contribute ────────────────────────────────────────────────────────
  describe("contribute", () => {
    beforeEach(async () => {
      await escrow.connect(creator).createPool(FIVE_POL, futureDeadline, 5);
    });

    it("creator can contribute", async () => {
      await expect(
        escrow.connect(creator).contribute(1, { value: ONE_POL })
      )
        .to.emit(escrow, "Contributed")
        .withArgs(1, creator.address, ONE_POL, ONE_POL);
    });

    it("new member auto-joins on first contribute", async () => {
      await escrow.connect(member1).contribute(1, { value: ONE_POL });
      expect(await escrow.isPoolMember(1, member1.address)).to.be.true;
      const [,,,, , memberCount,] = await escrow.getPool(1);
      expect(memberCount).to.equal(2); // creator + member1
    });

    it("multiple contributions tracked correctly", async () => {
      await escrow.connect(member1).contribute(1, { value: ONE_POL });
      await escrow.connect(member1).contribute(1, { value: TWO_POL });
      expect(await escrow.getContribution(1, member1.address)).to.equal(
        ONE_POL + TWO_POL
      );
    });

    it("rejects zero value", async () => {
      await expect(
        escrow.connect(member1).contribute(1, { value: 0 })
      ).to.be.revertedWith("Escrow: zero amount");
    });

    it("rejects contribution after deadline", async () => {
      await time.increase(8 * 24 * 60 * 60); // skip 8 days
      await expect(
        escrow.connect(member1).contribute(1, { value: ONE_POL })
      ).to.be.revertedWith("Escrow: deadline passed");
    });

    it("rejects contribution when pool full", async () => {
      // Create pool with max 2
      await escrow.connect(creator).createPool(FIVE_POL, futureDeadline, 2);
      await escrow.connect(member1).contribute(2, { value: ONE_POL }); // auto-joins, now 2/2
      await expect(
        escrow.connect(member2).contribute(2, { value: ONE_POL })
      ).to.be.revertedWith("Escrow: pool full");
    });
  });

  // ── completePool ──────────────────────────────────────────────────────
  describe("completePool", () => {
    beforeEach(async () => {
      await escrow.connect(creator).createPool(TWO_POL, futureDeadline, 5);
      await escrow.connect(creator).contribute(1, { value: ONE_POL });
      await escrow.connect(member1).contribute(1, { value: ONE_POL });
      // Now totalFunded = 2 POL = target
    });

    it("creator can complete when target is met", async () => {
      const balanceBefore = await ethers.provider.getBalance(creator.address);
      const tx = await escrow.connect(creator).completePool(1);
      const receipt = await tx.wait();
      const gasUsed = receipt.gasUsed * tx.gasPrice;
      const balanceAfter = await ethers.provider.getBalance(creator.address);

      expect(balanceAfter).to.be.closeTo(
        balanceBefore + TWO_POL - gasUsed,
        ethers.parseEther("0.001") // small tolerance
      );
    });

    it("emits PoolCompleted event", async () => {
      await expect(escrow.connect(creator).completePool(1))
        .to.emit(escrow, "PoolCompleted")
        .withArgs(1, creator.address, TWO_POL);
    });

    it("marks pool as completed", async () => {
      await escrow.connect(creator).completePool(1);
      const [,,,,,,completed] = await escrow.getPool(1);
      expect(completed).to.be.true;
    });

    it("non-creator cannot complete pool", async () => {
      await expect(
        escrow.connect(member1).completePool(1)
      ).to.be.revertedWith("Escrow: not creator");
    });

    it("rejects completion if target not met", async () => {
      // Create new underfunded pool
      await escrow.connect(creator).createPool(FIVE_POL, futureDeadline, 5);
      await escrow.connect(creator).contribute(2, { value: ONE_POL });
      await expect(
        escrow.connect(creator).completePool(2)
      ).to.be.revertedWith("Escrow: target not met");
    });

    it("rejects double completion", async () => {
      await escrow.connect(creator).completePool(1);
      await expect(
        escrow.connect(creator).completePool(1)
      ).to.be.revertedWith("Escrow: already completed");
    });
  });

  // ── refund ────────────────────────────────────────────────────────────
  describe("refund", () => {
    beforeEach(async () => {
      // Pool with target 5 POL, only 1 POL contributed → will expire
      await escrow.connect(creator).createPool(FIVE_POL, futureDeadline, 5);
      await escrow.connect(member1).contribute(1, { value: ONE_POL });
    });

    it("member gets refund after deadline if pool incomplete", async () => {
      await time.increase(8 * 24 * 60 * 60); // past deadline
      const balanceBefore = await ethers.provider.getBalance(member1.address);
      const tx = await escrow.connect(member1).refund(1);
      const receipt = await tx.wait();
      const gasUsed = receipt.gasUsed * tx.gasPrice;
      const balanceAfter = await ethers.provider.getBalance(member1.address);

      expect(balanceAfter).to.be.closeTo(
        balanceBefore + ONE_POL - gasUsed,
        ethers.parseEther("0.001")
      );
    });

    it("emits Refunded event", async () => {
      await time.increase(8 * 24 * 60 * 60);
      await expect(escrow.connect(member1).refund(1))
        .to.emit(escrow, "Refunded")
        .withArgs(1, member1.address, ONE_POL);
    });

    it("cannot refund before deadline", async () => {
      await expect(
        escrow.connect(member1).refund(1)
      ).to.be.revertedWith("Escrow: deadline not passed");
    });

    it("cannot refund if pool completed", async () => {
      // Fund to target first
      await escrow.connect(creator).contribute(1, { value: FIVE_POL });
      await escrow.connect(creator).completePool(1);
      await time.increase(8 * 24 * 60 * 60);
      await expect(
        escrow.connect(member1).refund(1)
      ).to.be.revertedWith("Escrow: already completed");
    });

    it("cannot double-refund", async () => {
      await time.increase(8 * 24 * 60 * 60);
      await escrow.connect(member1).refund(1);
      await expect(
        escrow.connect(member1).refund(1)
      ).to.be.revertedWith("Escrow: nothing to refund");
    });

    it("non-contributor has nothing to refund", async () => {
      await time.increase(8 * 24 * 60 * 60);
      await expect(
        escrow.connect(stranger).refund(1)
      ).to.be.revertedWith("Escrow: nothing to refund");
    });
  });
});
