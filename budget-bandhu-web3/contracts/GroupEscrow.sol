// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title GroupEscrow
 * @notice Multi-party escrow pool for BudgetBandhu group savings goals.
 *         Members contribute POL to a shared pool. Funds are locked until
 *         the target is reached. On completion, funds go to the pool creator.
 *         If the deadline passes without reaching the target, each member
 *         can individually withdraw (refund) their own contribution.
 *
 * @dev Gas-optimized:
 *      - No arrays in storage for members (only member count)
 *      - No loops in state-changing functions
 *      - Refund is user-triggered (no batch refund)
 *      - Minimal storage: numbers + mappings only
 */
contract GroupEscrow is ReentrancyGuard, Ownable {
    // ── Structs ──────────────────────────────────────────────────────────
    struct Pool {
        address creator;
        uint256 target;         // target amount in wei
        uint256 deadline;       // unix timestamp
        uint256 totalFunded;    // running total of contributions
        uint8   maxMembers;     // max allowed members
        uint8   memberCount;    // current member count
        bool    completed;      // funds released
    }

    // ── State ────────────────────────────────────────────────────────────
    uint256 public nextPoolId = 1;

    mapping(uint256 => Pool) public pools;
    mapping(uint256 => mapping(address => uint256)) public contributions;
    mapping(uint256 => mapping(address => bool)) public isMember;

    // ── Events ───────────────────────────────────────────────────────────
    event PoolCreated(
        uint256 indexed poolId,
        address indexed creator,
        uint256 target,
        uint256 deadline,
        uint8   maxMembers
    );
    event Contributed(
        uint256 indexed poolId,
        address indexed contributor,
        uint256 amount,
        uint256 newTotal
    );
    event PoolCompleted(
        uint256 indexed poolId,
        address indexed creator,
        uint256 totalAmount
    );
    event Refunded(
        uint256 indexed poolId,
        address indexed member,
        uint256 amount
    );

    // ── Constructor ──────────────────────────────────────────────────────
    constructor() Ownable(msg.sender) {}

    // ── Create Pool ──────────────────────────────────────────────────────
    /**
     * @notice Create a new escrow pool.
     * @param target     Target amount in wei.
     * @param deadline   Unix timestamp after which refunds are allowed.
     * @param maxMembers Maximum number of members (2-50).
     */
    function createPool(
        uint256 target,
        uint256 deadline,
        uint8   maxMembers
    ) external returns (uint256 poolId) {
        require(target > 0, "Escrow: zero target");
        require(deadline > block.timestamp, "Escrow: deadline in past");
        require(maxMembers >= 2 && maxMembers <= 50, "Escrow: members 2-50");

        poolId = nextPoolId++;

        pools[poolId] = Pool({
            creator:     msg.sender,
            target:      target,
            deadline:    deadline,
            totalFunded: 0,
            maxMembers:  maxMembers,
            memberCount: 1,
            completed:   false
        });

        isMember[poolId][msg.sender] = true;

        emit PoolCreated(poolId, msg.sender, target, deadline, maxMembers);
    }

    // ── Contribute ───────────────────────────────────────────────────────
    /**
     * @notice Contribute POL to a pool. First call also joins the pool.
     * @param poolId The pool to contribute to.
     */
    function contribute(uint256 poolId) external payable nonReentrant {
        Pool storage pool = pools[poolId];
        require(pool.creator != address(0), "Escrow: pool not found");
        require(!pool.completed, "Escrow: already completed");
        require(block.timestamp <= pool.deadline, "Escrow: deadline passed");
        require(msg.value > 0, "Escrow: zero amount");

        // Auto-join if not already a member
        if (!isMember[poolId][msg.sender]) {
            require(pool.memberCount < pool.maxMembers, "Escrow: pool full");
            isMember[poolId][msg.sender] = true;
            pool.memberCount += 1;
        }

        contributions[poolId][msg.sender] += msg.value;
        pool.totalFunded += msg.value;

        emit Contributed(poolId, msg.sender, msg.value, pool.totalFunded);
    }

    // ── Complete Pool ────────────────────────────────────────────────────
    /**
     * @notice Release pooled funds to the creator. Requires target reached.
     *         Only the pool creator can call this.
     */
    function completePool(uint256 poolId) external nonReentrant {
        Pool storage pool = pools[poolId];
        require(pool.creator == msg.sender, "Escrow: not creator");
        require(!pool.completed, "Escrow: already completed");
        require(pool.totalFunded >= pool.target, "Escrow: target not met");

        pool.completed = true;
        uint256 amount = pool.totalFunded;

        (bool sent, ) = payable(pool.creator).call{value: amount}("");
        require(sent, "Escrow: transfer failed");

        emit PoolCompleted(poolId, pool.creator, amount);
    }

    // ── Refund ───────────────────────────────────────────────────────────
    /**
     * @notice Refund individual contribution. Only available if:
     *         - Deadline has passed AND pool is NOT completed.
     *         Each user calls this for themselves (no batch refund).
     */
    function refund(uint256 poolId) external nonReentrant {
        Pool storage pool = pools[poolId];
        require(!pool.completed, "Escrow: already completed");
        require(block.timestamp > pool.deadline, "Escrow: deadline not passed");

        uint256 amount = contributions[poolId][msg.sender];
        require(amount > 0, "Escrow: nothing to refund");

        contributions[poolId][msg.sender] = 0;
        pool.totalFunded -= amount;

        (bool sent, ) = payable(msg.sender).call{value: amount}("");
        require(sent, "Escrow: refund failed");

        emit Refunded(poolId, msg.sender, amount);
    }

    // ── View Helpers ─────────────────────────────────────────────────────
    function getPool(uint256 poolId)
        external
        view
        returns (
            address creator,
            uint256 target,
            uint256 deadline,
            uint256 totalFunded,
            uint8   maxMembers,
            uint8   memberCount,
            bool    completed
        )
    {
        Pool storage p = pools[poolId];
        return (
            p.creator, p.target, p.deadline,
            p.totalFunded, p.maxMembers, p.memberCount,
            p.completed
        );
    }

    function getContribution(uint256 poolId, address user)
        external
        view
        returns (uint256)
    {
        return contributions[poolId][user];
    }

    function isPoolMember(uint256 poolId, address user)
        external
        view
        returns (bool)
    {
        return isMember[poolId][user];
    }
}
