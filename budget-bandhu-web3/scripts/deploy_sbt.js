const hre = require("hardhat");
const fs  = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying GoalBadgeSBT with:", deployer.address);
  console.log("Balance:", hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address)), "POL");

  // Cap gas price to avoid spikes — Amoy min is ~2.5 gwei, 35 gwei is safe ceiling
  const feeData   = await hre.ethers.provider.getFeeData();
  const gasPrice  = feeData.gasPrice ?? hre.ethers.parseUnits("30", "gwei");
  const MAX_GWEI  = hre.ethers.parseUnits("35", "gwei");
  const effectiveGasPrice = gasPrice < MAX_GWEI ? gasPrice : MAX_GWEI;
  console.log("Gas price:", hre.ethers.formatUnits(effectiveGasPrice, "gwei"), "gwei");

  const GoalBadgeSBT = await hre.ethers.getContractFactory("GoalBadgeSBT");
  const sbt = await GoalBadgeSBT.deploy({ gasPrice: effectiveGasPrice });
  await sbt.waitForDeployment();

  const address = await sbt.getAddress();
  console.log("\n✅ GoalBadgeSBT deployed to:", address);

  // Grant verifier role to backend wallet (from .env)
  const verifierWallet = process.env.VERIFIER_WALLET;
  if (verifierWallet) {
    console.log("Granting verifier role to:", verifierWallet);
    await sbt.setVerifier(verifierWallet, true);
    console.log("✅ Verifier role granted");
  } else {
    console.warn("⚠️  VERIFIER_WALLET not set in .env — grant manually after deploy");
  }

  // Save deployment info
  const deploymentInfo = {
    network: hre.network.name,
    GoalBadgeSBT: address,
    deployer: deployer.address,
    verifier: verifierWallet || null,
    deployedAt: new Date().toISOString(),
    txHash: sbt.deploymentTransaction()?.hash,
  };

  const outPath = path.join(__dirname, "../deployments/amoy.json");
  let existing = {};
  if (fs.existsSync(outPath)) {
    existing = JSON.parse(fs.readFileSync(outPath, "utf8"));
  }
  fs.writeFileSync(outPath, JSON.stringify({ ...existing, ...deploymentInfo }, null, 2));
  console.log("\n📝 Saved to deployments/amoy.json");
  console.log("\nNext step: run `npm run deploy:escrow` to deploy GroupEscrow");
}

main().catch((e) => { console.error(e); process.exit(1); });
