// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title GoalBadgeSBT
 * @notice Soulbound ERC-721 badge for BudgetBandhu goal achievements.
 *         Non-transferable — permanently bound to the recipient's wallet.
 *         Single contract handles badges for all goal types:
 *         Personal CSV, Personal Crypto, Group CSV, Group Escrow.
 * @dev Backend wallet is set as verifier and calls mintBadge / batchMintBadge.
 *      tokenURI points to IPFS (ipfs://CID) — no heavy data on-chain.
 */
contract GoalBadgeSBT is ERC721URIStorage, Ownable {
    // ── State ────────────────────────────────────────────────────────────
    uint256 private _nextTokenId = 1;

    /// @notice Addresses allowed to mint (owner + backend verifier wallets).
    mapping(address => bool) public verifiers;

    // ── Events ───────────────────────────────────────────────────────────
    event VerifierUpdated(address indexed verifier, bool allowed);
    event BadgeMinted(
        address indexed recipient,
        uint256 indexed tokenId,
        string goalTitle
    );

    // ── Modifiers ────────────────────────────────────────────────────────
    modifier onlyMinter() {
        require(
            owner() == _msgSender() || verifiers[_msgSender()],
            "GoalBadgeSBT: not owner or verifier"
        );
        _;
    }

    // ── Constructor ──────────────────────────────────────────────────────
    constructor()
        ERC721("BudgetBandhu Goal Badge", "BBGOAL")
        Ownable(msg.sender)
    {}

    // ── Admin ────────────────────────────────────────────────────────────
    function setVerifier(address verifier, bool allowed) external onlyOwner {
        require(verifier != address(0), "GoalBadgeSBT: zero address");
        verifiers[verifier] = allowed;
        emit VerifierUpdated(verifier, allowed);
    }

    // ── Minting ──────────────────────────────────────────────────────────
    function nextTokenId() external view returns (uint256) {
        return _nextTokenId;
    }

    /**
     * @notice Mint a single SBT badge.
     * @param recipient Wallet that receives the badge.
     * @param goalTitle Short title for event logging.
     * @param tokenUri  IPFS URI (ipfs://CID) pointing to metadata JSON.
     */
    function mintBadge(
        address recipient,
        string calldata goalTitle,
        string calldata tokenUri
    ) external onlyMinter returns (uint256 tokenId) {
        require(recipient != address(0), "GoalBadgeSBT: zero recipient");
        require(bytes(tokenUri).length > 0, "GoalBadgeSBT: empty URI");

        tokenId = _nextTokenId++;
        _safeMint(recipient, tokenId);
        _setTokenURI(tokenId, tokenUri);

        emit BadgeMinted(recipient, tokenId, goalTitle);
    }

    /**
     * @notice Mint badges to multiple recipients (group goals).
     *         Mints sequentially — no unbounded loops.
     * @param recipients Array of wallets (max 20 per call to avoid gas limit).
     * @param goalTitle  Shared goal title.
     * @param tokenUri   Shared IPFS URI.
     */
    function batchMintBadge(
        address[] calldata recipients,
        string calldata goalTitle,
        string calldata tokenUri
    ) external onlyMinter returns (uint256[] memory tokenIds) {
        require(recipients.length > 0, "GoalBadgeSBT: empty list");
        require(recipients.length <= 20, "GoalBadgeSBT: max 20 per batch");
        require(bytes(tokenUri).length > 0, "GoalBadgeSBT: empty URI");

        tokenIds = new uint256[](recipients.length);

        for (uint256 i = 0; i < recipients.length; i++) {
            require(recipients[i] != address(0), "GoalBadgeSBT: zero recipient");
            uint256 tokenId = _nextTokenId++;
            _safeMint(recipients[i], tokenId);
            _setTokenURI(tokenId, tokenUri);
            tokenIds[i] = tokenId;

            emit BadgeMinted(recipients[i], tokenId, goalTitle);
        }
    }

    // ── Soulbound: block ALL transfers ───────────────────────────────────

    /**
     * @dev Override the internal transfer hook. Only minting (from == address(0))
     *      is allowed. All wallet-to-wallet transfers are permanently blocked.
     */
    function _update(
        address to,
        uint256 tokenId,
        address auth
    ) internal override returns (address) {
        address from = _ownerOf(tokenId);

        // Allow minting (from == 0) and burning (to == 0), block transfers
        if (from != address(0) && to != address(0)) {
            revert("GoalBadgeSBT: non-transferable");
        }

        return super._update(to, tokenId, auth);
    }

    // ── Required overrides ───────────────────────────────────────────────
    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721URIStorage)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }
}
