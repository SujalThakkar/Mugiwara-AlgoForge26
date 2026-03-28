const hre = require("hardhat");
const fs  = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying GroupEscrow with:", deployer.address);

  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log("Balance:", hre.ethers.formatEther(balance), "POL");

  // ── Gas optimization: cap at 5 gwei (Amoy normally runs 1-2.5 gwei) ──
  const feeData  = await hre.ethers.provider.getFeeData();
  const gasPrice = feeData.gasPrice ?? hre.ethers.parseUnits("2", "gwei");
  const MAX_GWEI = hre.ethers.parseUnits("100", "gwei");

  if (gasPrice > MAX_GWEI) {
    console.error(`\n❌ Gas price too high: ${hre.ethers.formatUnits(gasPrice, "gwei")} gwei (max: 100 gwei)`);
    console.error("   Wait for gas to drop and try again.");
    process.exit(1);
  }

  const effectiveGasPrice = gasPrice < MAX_GWEI ? gasPrice : MAX_GWEI;
  console.log("Gas price:", hre.ethers.formatUnits(effectiveGasPrice, "gwei"), "gwei");

  // Estimate deployment cost (~1.2M gas for this contract)
  const estGas = 1_200_000n;
  const estCost = estGas * effectiveGasPrice;
  console.log("Estimated deploy cost:", hre.ethers.formatEther(estCost), "POL");

  if (balance < estCost) {
    console.error(`\n❌ Insufficient balance. Need ~${hre.ethers.formatEther(estCost)} POL`);
    process.exit(1);
  }

  const GroupEscrow = await hre.ethers.getContractFactory("GroupEscrow");
  const escrow = await GroupEscrow.deploy({ gasPrice: effectiveGasPrice });
  await escrow.waitForDeployment();

  const address = await escrow.getAddress();
  console.log("\n✅ GroupEscrow deployed to:", address);

  // Append to deployment info
  const outPath = path.join(__dirname, "../deployments/amoy.json");
  let existing = {};
  if (fs.existsSync(outPath)) {
    existing = JSON.parse(fs.readFileSync(outPath, "utf8"));
  }
  existing.GroupEscrow = address;
  existing.escrowDeployer = deployer.address;
  existing.escrowDeployedAt = new Date().toISOString();
  existing.escrowTxHash = escrow.deploymentTransaction()?.hash;

  fs.writeFileSync(outPath, JSON.stringify(existing, null, 2));
  console.log("\n📝 Saved to deployments/amoy.json");
  console.log("\n🎉 GroupEscrow deployed! Update frontend .env with:");
  console.log(`   NEXT_PUBLIC_ESCROW_ADDRESS=${address}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
