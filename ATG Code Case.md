# ATG Code Case

We would like to find out how good our customers are at picking the winning horse.

Using Python or Node.js, create a program which, for a given game-type, takes the three most recent games and lets an LLM answer the following:

- The three favourites from each leg - with name and v-odds,
- Whether or not the favourite horse won,
- The median finishing position of the favourite horse across all legs,
- How often does the favourite horse win?

The following end-points will be of use:

- `https://www.atg.se/services/racinginfo/v1/api/products/{gameType}` where the game-type can be, for example, `V85`, `V86`, `dd`, etc. E.g.: https://www.atg.se/services/racinginfo/v1/api/products/dd
- `https://www.atg.se/services/racinginfo/v1/api/games/{gameID}`
