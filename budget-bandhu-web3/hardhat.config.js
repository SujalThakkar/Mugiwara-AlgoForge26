require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
      evmVersion: "cancun",   // required for OZ v5 (uses mcopy opcode from EIP-5656)
    },
  },


  networks: {
    hardhat: {},

    amoy: {
      url: process.env.AMOY_RPC_URL || "https://rpc-amoy.polygon.technology",
      accounts: process.env.DEPLOYER_PRIVATE_KEY
        ? [process.env.DEPLOYER_PRIVATE_KEY]
        : [],
      gasPrice: "auto",
      gas: "auto",
    },
  },

  etherscan: {
    apiKey: {
      polygonAmoy: process.env.POLYGONSCAN_API_KEY || "",
    },
    customChains: [
      {
        network: "polygonAmoy",
        chainId: 80002,
        urls: {
          apiURL: "https://api-amoy.polygonscan.com/api",
          browserURL: "https://amoy.polygonscan.com",
        },
      },
    ],
  },
};
