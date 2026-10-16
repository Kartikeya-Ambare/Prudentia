/**
 * Interface copy, English only. (Chat understands English and Hinglish on its own; the app does not
 * switch language.) Kept as a keyed dictionary so every string lives in one place.
 */
const D = {
  tagline: "Where should your money go?",
  modeBeginner: "Beginner", modeExpert: "Expert",
  modeBeginnerHint: "Chat your way to a plan", modeExpertHint: "Set every detail yourself",
  modes: "Experience level",
  navHome: "Recommendation", pageHome: "Asset Allocation Recommendation",
  navLocked: "Available after you get a recommendation",
  navStocks: "Stocks", navMf: "Mutual funds", navFd: "Fixed deposits", navSectors: "Fund sectors",
  nav: "Main navigation",
  disclaimer: "Estimates from past data, not investment advice. Returns are not guaranteed.",
  amount: "Amount you can invest (Rs.)", years: "For how many years", risk: "Risk you can afford (%)",
  riskLow: "Low", riskMod: "Moderate", riskHigh: "High",
  riskHelp: "How big a drop you could live with. Higher means more stocks.",
  assetClasses: "Where to invest", stocks: "Stocks", mf: "Mutual funds", fd: "Bank FDs",
  pickOne: "Keep at least one selected.",
  sectorPref: "Stock sectors (optional)", mfPref: "Fund categories (optional)",
  banks: "Banks for FDs", banksAuto: "Auto: best 5", banksPick: "I will choose", banksPickHelp: "Pick the banks you want.",
  banksNeedOne: "Choose at least one bank.",
  ownSplit: "Set my own split", splitTotal: "Total", splitMust: "Must add up to 100%.",
  getPlan: "Get my plan", updatePlan: "Update plan",
  failed: "Could not build the plan",
  summary: "Your plan",
  afterTax: "after tax", perYear: "per year",
  invested: "Invested", horizon: "Time frame", yearsUnit: "years", dataAsOf: "Prices as of",
  scenarios: "What it could grow to",
  bear: "Cautious case", base: "Expected case", bull: "Optimistic case",
  scenarioNote: "Scenarios from the model, not promises.",
  byClass: "Money by asset class", weights: "Every holding", projections: "Today vs. at the end", banksSel: "Your FDs",
  colName: "Name", colType: "Type", colShare: "Share", colAmount: "Amount (Rs.)", colNow: "Today (Rs.)",
  colLater: "Later (Rs.)", colReturn: "Yearly return %",
  share: "Share of plan", projected: "Projected value", today: "Invested today", yearlyReturn: "Yearly return",
  notInPlan: "isn't part of your plan right now.",
  notInPlanHow: "Add it from the Recommendation page, or ask the chat.",
  noPlanYet: "No plan yet",
  noPlanHow: "Create a plan on the Recommendation page and this page fills in.",
  chat: "Plan chat",
  chatEdit: "Your plan is ready. Ask me to change the amount, years or risk, move money between stocks, funds and FDs, or add or remove one.",
  chatIntro: "Prefer to talk it through? Tell me the amount, the years and how much risk you can take, and I will build the plan.",
  chatPlaceholder: "Message Prudie…", send: "Send", thinking: "Working on it…",
  startHeading: "What would you like to invest?",
  startSub: "Share the amount, how long and how much risk you can take.",
  startPlaceholder: "e.g. I want to invest Rs. 5 lakh for 5 years with 50% risk",
  riskAsk: "Answer:",
  chatDown: "Chat is not reachable right now. Switch to Expert to use the form instead.",
  chatSlow: "Please wait a second between messages.",
  starterEmpty: "Your plan will appear here once we have your amount, years and risk.",
  backendDown: "Backend not reachable. Start it first:",
  drifted: "Prices have moved since this plan was made. Ask chat to check it.",
  kpiReturn: "Return", kpiVol: "Volatility", kpiHorizon: "Horizon", kpiPrices: "Prices",
  viewChart: "Chart", viewTable: "Table", showAll: "Show all", showTop: "Show top",
  allocationByClass: "Where your money goes",
  loaderTitle: "Prudie is working out your plan",
  loaderSteps: "Reading the latest prices|Picking stocks and funds|Choosing FD banks|Running the scenarios",
  chatOpen: "Chat with Prudie", chatClose: "Close chat",
 
  stocksBlurb: "Individual company shares", mfBlurb: "Professionally managed funds", fdBlurb: "Fixed deposits with banks",
  sectorsAsOf: "Fund holdings as of", sectorsNone: "Sector breakdown for this fund is not available yet. It appears here once the fund house publishes its monthly portfolio and we load it.",
  sectorsIntro: "Sector breakdown of the mutual funds in your plan. Fund holdings change slowly, so these come from the latest saved snapshot.",
} as const;

export type Key = keyof typeof D;

export function useT() {
  return (k: Key): string => D[k];
}
