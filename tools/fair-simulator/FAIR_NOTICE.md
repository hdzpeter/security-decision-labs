# FAIR Methodology Notice

## About FAIR

This tool implements the **Factor Analysis of Information Risk (FAIR)** methodology, an international standard for cyber risk quantification.

FAIR provides a framework for understanding, analyzing, and quantifying information risk in financial terms.

## Trademark and Affiliation

**FAIR** and the **FAIR Institute logo** are registered trademarks of the FAIR Institute.

### This Software Is:

- **NOT affiliated** with the FAIR Institute
- **NOT endorsed** by the FAIR Institute  
- **NOT certified** by the FAIR Institute
- **An independent implementation** of the FAIR methodology

This is an independent, open-source implementation created for educational and/or research purposes.

## Official FAIR Resources

For official FAIR training, certification, and authoritative resources:

- **FAIR Institute:** https://www.fairinstitute.org/
- **FAIR Training and Certification:** https://www.fairinstitute.org/fair-training-and-certification

## Data Sources

This tool incorporates benchmark data from:

**IRIS 2025 (Information Risk Insights Study)**
- **Author:** Cyentia Institute (https://www.cyentia.com/)
- **Access:** Available at https://www.cyentia.com/iris2025/
- **Usage:** Statistical parameters extracted with full source attribution
- **Purpose:** "To aid community efforts to manage cyber risk" (IRIS 2025, p. 2)

**Data Extracted:**
- Annual incident probabilities by industry/revenue (Figures 7, 8)
- Median and 95th percentile losses by sector/revenue (Tables 1, Figure A3)
- Loss distribution parameters for FAIR scenario calibration

**Full Citation:**
Cyentia Institute. (2025). *Information Risk Insights Study 2025: It's About Time*. 
Sponsored by the Cybersecurity and Infrastructure Security Agency (CISA). 
Retrieved from https://www.cyentia.com/iris2025/
Users must comply with the respective licenses and terms of use for all data sources.

## Implementation Notes

This implementation follows the FAIR specification as documented in:
- *"Measuring and Managing Information Risk: A FAIR Approach"* by Jack Freund and Jack Jones
- FAIR Institute's technical guidance and best practices

Any deviations from or extensions to the standard FAIR methodology are documented in this repository.

## Frontend Dependencies

The React/Vite frontend implementation includes:
- **shadcn/ui components** - used under [MIT License](https://github.com/shadcn-ui/ui/blob/main/LICENSE.md)
- **Unsplash photos** - used under [Unsplash License](https://unsplash.com/license)

**Design:**
- UI mockups created in **Figma**

## Questions About FAIR

For questions about:
- **The FAIR methodology itself:** Contact the FAIR Institute
- **This specific implementation:** Open an issue in this repository