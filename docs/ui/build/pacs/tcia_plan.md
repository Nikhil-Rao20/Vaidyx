# TCIA source plan for the Vaidyx tumour board demo PACS

Prepared 2026-10-18. Research and planning only: no image data has been downloaded, no repo file touched. All API calls were made from this machine with curl or Python urllib against the public NBIA endpoints (no login). Words to search for in this file: "not verified" marks anything I could not confirm, "FACE CHECK" marks series that may include part of the face.

## 0. Summary

- The public TCIA API answers from here (HTTP 200, about 7 s for the collection list, 1 to 3 s per metadata call). Base used: https://services.cancerimagingarchive.net/nbia-api/services/v1/ (v1). The newer v4 base https://nbia.cancerimagingarchive.net/nbia-api/services/v4/ also answers without a token and adds getDicomTags, which I used to read header tags of every chosen series without downloading pixels.
- 19 collections chosen, all verified on their TCIA collection page AND in the API LicenseName field as CC BY 3.0 Unported or CC BY 4.0 International. No NC, no restricted, no data use agreement.
- 71 series, 30 source patients plus 1 reserve patient (31 in total), 43 studies, total 4.23 GB uncompressed DICOM (TCIA FileSize); the zips compress about 2 to 1, so expect about 2.5 GB on the wire. Well under the 15 GB target, which leaves room for the reserve rows and extra series if the doctors ask for more.
- Every chosen series has BurnedInAnnotation = NO or absent and PatientIdentityRemoved = YES in its header. No InstitutionName is present. All carry private tags (TCIA CTP group 0013 plus vendor groups) that we will strip.
- Big caveat, head and neck: since January 2022 every TCIA head and neck image collection (HNSCC, Head-Neck-PET-CT, QIN-HEADNECK, CPTAC-HNSCC, TCGA-HNSC, ACRIN-HNSCC-FDG-PET-CT images, HNSCC-3DCT-RT, RADCURE, OPC-Radiomics, HEAD-NECK-RADIOMICS-HN1) is under the "NIH Controlled Data Access Policy" (dbGaP request, approval, data use agreement) because the images could reconstruct a face. None of them is allowed by the hard rule. The oral cavity group therefore uses stand-in neck CT and PET-CT series from CC BY collections whose patients are not head and neck cancer patients. These must be labelled as stand-ins in the manifest and in any clinical story shown to the doctors.
- Three chosen collections are of Chinese origin (CMMD, Lung-PET-CT-Dx, StageII-Colorectal-CT). They are tagged "China" in the tables, per the report labelling rule.

## 1. Chosen collections (all verified)

Licence column: the short form shown in the Data Access table of the TCIA collection page, and in brackets the exact LicenseName string returned by the API getSeries call for every series of that collection. The licence URL is the link the page uses. Verification date for all pages: 2026-10-18.

| Collection | Licence (page, and API LicenseName) | Licence URL | Modalities (API) | Body part (API) | Collection DOI | TCIA page | Origin and notes |
|---|---|---|---|---|---|---|---|
| CMMD | CC BY 4.0 (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | MG | BREAST | https://doi.org/10.7937/tcia.eqde-4b16 | https://www.cancerimagingarchive.net/collection/cmmd/ | China (South China University of Technology volunteers; hospital not named on page) |
| TCGA-BRCA | CC BY 3.0 (Creative Commons Attribution 3.0 Unported License) | https://creativecommons.org/licenses/by/3.0/ | MG, MR, SR | BREAST | https://doi.org/10.7937/K9/TCIA.2016.AB2NAZRP | https://www.cancerimagingarchive.net/collection/tcga-brca/ | USA (TCGA sites). TCGA acknowledgement sentence requested, see section 5 |
| CMB-BRCA | CC BY 4.0 (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, MG, MR, PT, US | BREAST, CHEST, ABDOMEN and others | https://doi.org/10.7937/dx22-8j71 | https://www.cancerimagingarchive.net/collection/cmb-brca/ | USA. Version 6 has no restricted portion left |
| Lung-PET-CT-Dx | CC BY 4.0 (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, PT | CHEST, ABDOMEN (whole body PET) | https://doi.org/10.7937/TCIA.2020.NNC2-0461 | https://www.cancerimagingarchive.net/collection/lung-pet-ct-dx/ | China (Second Affiliated Hospital of Harbin Medical University). Patient prefix A = adenocarcinoma, G = squamous, B = small cell, E = large cell (from the collection description; not re-verified in this session) |
| NSCLC Radiogenomics | CC BY 3.0 (Creative Commons Attribution 3.0 Unported License) | https://creativecommons.org/licenses/by/3.0/ | CT, PT, SEG | CHEST (CT), whole body PET-CT | https://doi.org/10.7937/K9/TCIA.2017.7hs46erv | https://www.cancerimagingarchive.net/collection/nsclc-radiogenomics/ | USA (Stanford, VA Palo Alto) |
| CPTAC-LUAD | CC BY 4.0 (Version 13 Data Access table; earlier versions CC BY 3.0) (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, MR, PT | CHEST, NECK, WHOLEBODY and others | https://doi.org/10.7937/K9/TCIA.2018.PAT12TBS | https://www.cancerimagingarchive.net/collection/cptac-luad/ | Multi-site, mostly USA and international CPTAC sites |
| TCGA-LUAD | CC BY 3.0 (Creative Commons Attribution 3.0 Unported License) | https://creativecommons.org/licenses/by/3.0/ | CT, PT, NM | CHEST, LUNG | https://doi.org/10.7937/K9/TCIA.2016.JGNIHEP5 | https://www.cancerimagingarchive.net/collection/tcga-luad/ | USA (TCGA sites). TCGA acknowledgement sentence requested |
| LIDC-IDRI | CC BY 3.0 (Creative Commons Attribution 3.0 Unported License) | https://creativecommons.org/licenses/by/3.0/ | CT, CR, DX (plus third party SEG, SR) | CHEST | https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX | https://www.cancerimagingarchive.net/collection/lidc-idri/ | USA, 7 academic centres |
| TCGA-CESC | CC BY 3.0 (Creative Commons Attribution 3.0 Unported License) | https://creativecommons.org/licenses/by/3.0/ | MR | CERVIX | https://doi.org/10.7937/K9/TCIA.2016.SQ4M8YP4 | https://www.cancerimagingarchive.net/collection/tcga-cesc/ | Brazil (study descriptions in Portuguese). TCGA acknowledgement sentence requested |
| CC-Tumor-Heterogeneity | CC BY 4.0 (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, MR, PT, REG, RTSTRUCT | PELVIS | https://doi.org/10.7937/ERZ5-QZ59 | https://www.cancerimagingarchive.net/collection/cc-tumor-heterogeneity/ | USA; 23 patients, stage IB2 to IVA cervical cancer |
| TCGA-READ | CC BY 3.0 (Creative Commons Attribution 3.0 Unported License) | https://creativecommons.org/licenses/by/3.0/ | CT, MR | RECTUM | https://doi.org/10.7937/K9/TCIA.2016.F7PPNPNU | https://www.cancerimagingarchive.net/collection/tcga-read/ | USA (TCGA sites), only 3 patients. TCGA acknowledgement sentence requested |
| TCGA-COAD | CC BY 3.0 (Creative Commons Attribution 3.0 Unported License) | https://creativecommons.org/licenses/by/3.0/ | CT (one OT) | COLON | https://doi.org/10.7937/K9/TCIA.2016.HJJHBOXZ | https://www.cancerimagingarchive.net/collection/tcga-coad/ | USA (TCGA sites). TCGA acknowledgement sentence requested |
| Colorectal-Liver-Metastases | CC BY 4.0 (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, SEG | ABDOMEN (portal venous CT) | https://doi.org/10.7937/QXK2-QG03 | https://www.cancerimagingarchive.net/collection/colorectal-liver-metastases/ | USA (Memorial Sloan Kettering) |
| StageII-Colorectal-CT | CC BY 4.0 (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT | ABDOMEN, PELVIS | https://doi.org/10.7937/p5k5-tg43 | https://www.cancerimagingarchive.net/collection/stageii-colorectal-ct/ | China (page: follows the ethical and privacy rules of China; NSFC funded) |
| CMB-CRC | CC BY 4.0 for the public portion used here (head images are under the NIH Controlled Data Access Policy and are not used) (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, MR, PT, US, DX, NM, XA | ABDOMEN, CHEST, PELVIS, CHESTABDPELVIS and others | https://doi.org/10.7937/DJG7-GZ87 | https://www.cancerimagingarchive.net/collection/cmb-crc/ | USA |
| CMB-LCA | CC BY 4.0 for the public portion used here (head images restricted, not used) (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, MR, PT, NM, US, DX | CHEST, ABDOMEN, CHESTABDPELVIS and others | https://doi.org/10.7937/3CX3-S132 | https://www.cancerimagingarchive.net/collection/cmb-lca/ | USA |
| Mediastinal-Lymph-Node-SEG | CC BY 4.0 (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, SEG | CHEST, CHESTABDPELVIS, NECK, ABDOMEN | https://doi.org/10.7937/QVAZ-JA09 | https://www.cancerimagingarchive.net/collection/mediastinal-lymph-node-seg/ | USA; 513 patients with lymphadenopathy from many cancer types including head and neck cancer |
| FDG-PET-CT-Lesions | CC BY 4.0 for the defaced images and clinical data (the non-defaced images are under the NIH Controlled Data Access Policy; the public API serves only the defaced set) (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, PT, SEG | WHOLEBODY | https://doi.org/10.7937/gkr0-xv29 | https://www.cancerimagingarchive.net/collection/fdg-pet-ct-lesions/ | Germany (Tuebingen); lymphoma, melanoma, NSCLC and negative controls |
| CPTAC-PDA | CC BY 4.0 (Version 15) (Creative Commons Attribution 4.0 International License) | https://creativecommons.org/licenses/by/4.0/ | CT, MR, PT, US, RTSTRUCT | ABDOMEN, PANCREAS, CHESTABDPELVIS and others | https://doi.org/10.7937/K9/TCIA.2018.SC20FO18 | https://www.cancerimagingarchive.net/collection/cptac-pda/ | Multi-site CPTAC |

How to cite each collection (copy for the about page). The TCIA rule (Data Usage Policies page) is: cite the dataset with its full data citation and DOI link every time the data are used, and cite TCIA itself with the Clark et al. 2013 paper.

- CMMD: Cui, C., Li, L., Cai, H., Fan, Z., Zhang, L., Dan, T., Li, J., & Wang, J. (2021). The Chinese Mammography Database (CMMD): An online mammography database with biopsy confirmed types for machine diagnosis of breast [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/tcia.eqde-4b16
- TCGA-BRCA: Lingle, W., Erickson, B. J., Zuley, M. L., Jarosz, R., Bonaccio, E., Filippini, J., Net, J. M., Levi, L., Morris, E. A., Figler, G. G., Elnajjar, P., Kirk, S., Lee, Y., Giger, M., & Gruszauskas, N. (2016). The Cancer Genome Atlas Breast Invasive Carcinoma Collection (TCGA-BRCA) (Version 3) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2016.AB2NAZRP
- CMB-BRCA: Cancer Moonshot Biobank. (2024). Cancer Moonshot Biobank - Invasive Breast Carcinoma Cancer Collection (CMB-BRCA) (Version 6) [dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/dx22-8j71
- Lung-PET-CT-Dx: Li, P., Wang, S., Li, T., Lu, J., HuangFu, Y., & Wang, D. (2020). A Large-Scale CT and PET/CT Dataset for Lung Cancer Diagnosis (Lung-PET-CT-Dx) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/TCIA.2020.NNC2-0461
- NSCLC Radiogenomics: Bakr, S., Gevaert, O., Echegaray, S., Ayers, K., Zhou, M., Shafiq, M., Zheng, H., Zhang, W., Leung, A., Kadoch, M., Shrager, J., Quon, A., Rubin, D., Plevritis, S., & Napel, S. (2017). Data for NSCLC Radiogenomics (Version 4) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2017.7hs46erv
- CPTAC-LUAD: National Cancer Institute Clinical Proteomic Tumor Analysis Consortium (CPTAC). (2018). The Clinical Proteomic Tumor Analysis Consortium Lung Adenocarcinoma Collection (CPTAC-LUAD) (Version 13) [dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/k9/tcia.2018.pat12tbs
- TCGA-LUAD: Albertina, B., Watson, M., Holback, C., Jarosz, R., Kirk, S., Lee, Y., Rieger-Christ, K., & Lemmerman, J. (2016). The Cancer Genome Atlas Lung Adenocarcinoma Collection (TCGA-LUAD) (Version 4) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2016.JGNIHEP5
- LIDC-IDRI: Armato III, S. G., McLennan, G., Bidaut, L., McNitt-Gray, M. F., Meyer, C. R., Reeves, A. P., ... Clarke, L. P. (2015). Data From LIDC-IDRI [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX (57 author names on the page; copy the full list from the page for the about page)
- TCGA-CESC: Lucchesi, F. R., & Aredes, N. D. (2016). The Cancer Genome Atlas Cervical Squamous Cell Carcinoma and Endocervical Adenocarcinoma Collection (TCGA-CESC) (Version 3) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2016.SQ4M8YP4
- CC-Tumor-Heterogeneity: Mayr, N., and nine co-authors (2023). Cervical Cancer - Tumor Heterogeneity: Serial Functional and Molecular Imaging Across the Radiation Therapy Course in Advanced Cervical Cancer (CC-Tumor-Heterogeneity) (Version 1) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/ERZ5-QZ59 (co-author names not captured by the page fetch; copy from the page)
- TCGA-READ: Kirk, S., Lee, Y., Sadow, C. A., & Levine, S. (2016). The Cancer Genome Atlas Rectum Adenocarcinoma Collection (TCGA-READ) (Version 3) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2016.F7PPNPNU
- TCGA-COAD: Kirk, S., Lee, Y., Sadow, C. A., Levine, S., Roche, C., Bonaccio, E., & Filiippini, J. (2016). The Cancer Genome Atlas Colon Adenocarcinoma Collection (TCGA-COAD) (Version 3) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/K9/TCIA.2016.HJJHBOXZ (the page spells the last author Filiippini in the citation)
- Colorectal-Liver-Metastases: Simpson, A. L., Peoples, J., Creasy, J. M., Fichtinger, G., Gangai, N., Lasso, A., Keshava Murthy, K. N., Shia, J., D'Angelica, M. I., & Do, R. K. G. (2023). Preoperative CT and Survival Data for Patients Undergoing Resection of Colorectal Liver Metastases (Colorectal-Liver-Metastases) (Version 2) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/QXK2-QG03
- StageII-Colorectal-CT: Tong, T., & Li, M. (2022). Abdominal or pelvic enhanced CT images within 10 days before surgery of 230 patients with stage II colorectal cancer (StageII-Colorectal-CT) [Dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/p5k5-tg43
- CMB-CRC: Cancer Moonshot Biobank. (2022). Cancer Moonshot Biobank - Colorectal Cancer Collection (CMB-CRC) (Version 11) [dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/djg7-gz87
- CMB-LCA: Cancer Moonshot Biobank. (2022). Cancer Moonshot Biobank - Lung Cancer Collection (CMB-LCA) (Version 12) [dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/3cx3-s132
- Mediastinal-Lymph-Node-SEG: Idris, T., Somarouthu, S., Jacene, H., LaCasce, A., Ziegler, E., Pieper, S., Khajavi, R., Dorent, R., Pujol, S., Kikinis, R., & Harris, G. (2024). Mediastinal Lymph Node Quantification (LNQ): Segmentation of Heterogeneous CT Data (Version 1) [Data set]. The Cancer Imaging Archive. https://doi.org/10.7937/QVAZ-JA09
- FDG-PET-CT-Lesions: Gatidis, S., & Kuestner, T. (2022). A whole-body FDG-PET/CT dataset with manually annotated tumor lesions (FDG-PET-CT-Lesions) (Version 2) [dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/gkr0-xv29
- CPTAC-PDA: National Cancer Institute Clinical Proteomic Tumor Analysis Consortium (CPTAC). (2018). The Clinical Proteomic Tumor Analysis Consortium Pancreatic Ductal Adenocarcinoma Collection (CPTAC-PDA) (Version 15) [dataset]. The Cancer Imaging Archive. https://doi.org/10.7937/k9/tcia.2018.sc20fo18

TCIA general citation: Clark, K., Vendt, B., Smith, K., Freymann, J., Kirby, J., Koppel, P., Moore, S., Phillips, S., Maffitt, D., Pringle, M., Tarbox, L., & Prior, F. (2013). The Cancer Imaging Archive (TCIA): Maintaining and Operating a Public Information Repository. Journal of Digital Imaging, 26(6), 1045 to 1057. https://doi.org/10.1007/s10278-013-9622-7 (first six and last author confirmed from the TCIA policy page in this session; the middle names are the standard citation and were not re-read from the page, so mark them "not verified" until copied from https://www.cancerimagingarchive.net/data-usage-policies-and-restrictions/).

TCGA acknowledgement (TCGA-BRCA, TCGA-LUAD, TCGA-CESC, TCGA-READ, TCGA-COAD pages ask publications to include it): "The results shown here are in whole or part based upon data generated by the TCGA Research Network: https://www.cancer.gov/tcga."

### 1b. Verified but excluded, and verified but not needed

| Collection | Finding | Decision |
|---|---|---|
| HNSCC | Images and RT structures: "NIH Controlled Data Access Policy" (only clinical data CC BY 3.0). Page: https://www.cancerimagingarchive.net/collection/hnscc/ . Not returned by the public API. | Excluded (restricted) |
| Head-Neck-PET-CT | Images: NIH Controlled Data Access Policy; clinical data CC BY 3.0. https://www.cancerimagingarchive.net/collection/head-neck-pet-ct/ | Excluded (restricted) |
| QIN-HEADNECK | Images and segmentations: NIH Controlled Data Access Policy; clinical CC BY 3.0. https://www.cancerimagingarchive.net/collection/qin-headneck/ | Excluded (restricted) |
| CPTAC-HNSCC | NIH Controlled Data Access Policy for all versions. https://www.cancerimagingarchive.net/collection/cptac-hnscc/ | Excluded (restricted) |
| TCGA-HNSC | NIH Controlled Data Access Policy. https://www.cancerimagingarchive.net/collection/tcga-hnsc/ | Excluded (restricted) |
| ACRIN-HNSCC-FDG-PET-CT | Public API returns only RTSTRUCT series (2085), no images; images not public. Page not fetched. | Excluded (images not public; licence of images not verified) |
| HNSCC-3DCT-RT, RADCURE, OPC-Radiomics, HEAD-NECK-RADIOMICS-HN1 | Not in the public collection list of the API. A TCIA access guide found by web search lists them as restricted licence collections; HN1 as "TCIA No Commercial Use Limited Access License". Pages not fetched. | Excluded (not verified on page, but not public either way) |
| Duke-Breast-Cancer-MRI | "CC BY-NC 4.0" on the page. https://www.cancerimagingarchive.net/collection/duke-breast-cancer-mri/ | Excluded (NC) |
| NSCLC-Radiomics (Lung1) | Known as CC BY-NC 3.0; page not fetched in this session. | Excluded (not verified, assumed NC) |
| CBIS-DDSM | CC BY 3.0 verified (https://www.cancerimagingarchive.net/collection/cbis-ddsm/, DOI 10.7937/K9/TCIA.2016.7O02S9CY). Scanned film mammograms, one image per series, "patient" IDs are per view. | Allowed, kept as backup for extra mammograms; CMMD, TCGA-BRCA and CMB-BRCA give digital mammograms already |
| HCC-TACE-Seg | CC BY 4.0 verified (DOI 10.7937/TCIA.5FNA-0924). Liver HCC CT. | Allowed, not needed for the six groups |
| CPTAC-LSCC | CC BY 4.0 verified for the public portion (head subset restricted). Squamous NSCLC CT and PET. | Allowed, reserve for a squamous lung case |
| TCGA-LUSC | CC BY 3.0 verified (DOI 10.7937/K9/TCIA.2016.TYGKKFMQ). | Allowed, reserve |
| ACRIN-NSCLC-FDG-PET | CC BY 3.0 verified (DOI 10.7937/tcia.2019.30ilqfcl). 242 patients, CT and PET. | Allowed, reserve for more lung PET-CT |
| Anti-PD-1_Lung | CC BY 3.0 verified (DOI 10.7937/tcia.2019.zjjwb9ip). | Allowed, reserve |
| RIDER Lung PET-CT | CC BY 3.0 verified (DOI 10.7937/k9/tcia.2015.ofip7tvm). | Allowed, reserve |
| CT Lymph Nodes | CC BY 3.0 verified (DOI 10.7937/K9/TCIA.2015.AQIIDCNM). Series mostly over 400 images. | Allowed, not used (large series) |
| BREAST-DIAGNOSIS | CC BY 3.0 verified (DOI 10.7937/K9/TCIA.2015.SDNRQXXR). MR, MG, CT, PT. | Allowed, reserve |
| Advanced-MRI-Breast-Lesions | CC BY 4.0 verified (DOI 10.7937/C7X1-YN57). 632 breast MR patients. | Allowed, reserve for breast MRI |
| ISPY1 | CC BY 3.0 verified (DOI 10.7937/K9/TCIA.2016.HdHpgJLK). | Allowed, reserve |
| ACRIN-6698 | CC BY 4.0 verified (DOI 10.7937/tcia.kk02-6d95). | Allowed, reserve |
| QIN-BREAST | CC BY 3.0 verified (DOI 10.7937/K9/TCIA.2016.21JUEBH0). | Allowed, reserve |

## 2. Concrete picks per cancer group

Columns: demo slot, source collection, source PatientID, age and sex in the source header (to be replaced), StudyDate as stored by TCIA (already shifted by TCIA, will be shifted again by us), StudyInstanceUID, SeriesInstanceUID, modality, SeriesDescription, image count, size in MB (TCIA FileSize, uncompressed). "Header check" is from v4 getDicomTags: BIA = BurnedInAnnotation (0028,0301), priv = number of private tags seen in one representative image.

### A Breast: 5 source patients, 11 series, 0.54 GB

| Slot | Collection | PatientID | Age/sex (source) | StudyDate (source) | StudyInstanceUID | SeriesInstanceUID | Mod | SeriesDescription | Images | MB | Header check | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BR-01 | CMMD | D1-0001 | 044Y/F | 2010-07-18 | 1.3.6.1.4.1.14519.5.2.1.1239.1759.335790956129760663091398779377 | 1.3.6.1.4.1.14519.5.2.1.1239.1759.623006463861567934606116970244 | MG | None | 2 | 8.8 | BIA=NO, IdRemoved=YES, priv=3 | FFDM, 2 views one side (China) |
| BR-02 | CMMD | D2-0140 | 058Y/F | 2010-07-18 | 1.3.6.1.4.1.14519.5.2.1.1239.1759.598888059044635576254843278173 | 1.3.6.1.4.1.14519.5.2.1.1239.1759.115060983843511037348481244160 | MG | None | 4 | 17.6 | BIA=NO, IdRemoved=YES, priv=3 | FFDM, 4 views bilateral (China) |
| BR-03 | TCGA-BRCA | TCGA-AO-A0JI | 056Y/F | 2001-05-05 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.167926431715892466505720332428 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.997993139263721918674259792020 | MG | DIAG MAMMOGRAM U | 2 | 17.6 | BIA=NO, IdRemoved=YES, priv=4 | diagnostic MG (2 series) + breast MR T2 and post contrast |
| BR-03 | TCGA-BRCA | TCGA-AO-A0JI | 056Y/F | 2001-05-05 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.167926431715892466505720332428 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.819947422704003839421250353099 | MG | DIAG MAMMOGRAM U | 2 | 17.6 | BIA=NO, IdRemoved=YES, priv=4 | diagnostic MG (2 series) + breast MR T2 and post contrast |
| BR-03 | TCGA-BRCA | TCGA-AO-A0JI | 056Y/F | 2001-11-06 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.269421353089726166053369880329 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.112501477437352839202306368352 | MR | T2 left breast | 46 | 6.3 | BIA=NO, IdRemoved=YES, priv=160 | diagnostic MG (2 series) + breast MR T2 and post contrast |
| BR-03 | TCGA-BRCA | TCGA-AO-A0JI | 056Y/F | 2001-11-06 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.269421353089726166053369880329 | 1.3.6.1.4.1.14519.5.2.1.9203.4002.179993109981592527027438512275 | MR | Ax Vibrant post | 62 | 32.8 | BIA=NO, IdRemoved=YES, priv=160 | diagnostic MG (2 series) + breast MR T2 and post contrast |
| BR-04 | CMB-BRCA | MSB-08876 | n/a/O | 1950-12-30 | 1.3.6.1.4.1.14519.5.2.1.144734068299006541363548570440590809268 | 1.3.6.1.4.1.14519.5.2.1.207776098961005429284467902411167871841 | MG | Diagnostic digital bilateral mammo | 4 | 58.7 | BIA=NO, IdRemoved=YES, priv=28 | bilateral diagnostic MG + CT chest |
| BR-04 | CMB-BRCA | MSB-08876 | n/a/O | 1959-04-18 | 1.3.6.1.4.1.14519.5.2.1.248421274998286136526119942490393006821 | 1.3.6.1.4.1.14519.5.2.1.154688781059619045804962302064173369383 | CT | 2.5MM STD 50% ASIR | 117 | 61.9 | BIA=absent, IdRemoved=YES, priv=123 | bilateral diagnostic MG + CT chest |
| BR-05 | CMB-BRCA | MSB-07863 | n/a/O | 1959-02-14 | 1.3.6.1.4.1.14519.5.2.1.272076958914307983784680472643113270097 | 1.3.6.1.4.1.14519.5.2.1.155063585747407232218562393551620497758 | MR | Ax T2 FSE STIR | 54 | 113.6 | BIA=absent, IdRemoved=YES, priv=204 | breast MR STIR + DCE phase 1 + CT chest-abdomen-pelvis |
| BR-05 | CMB-BRCA | MSB-07863 | n/a/O | 1959-02-14 | 1.3.6.1.4.1.14519.5.2.1.272076958914307983784680472643113270097 | 1.3.6.1.4.1.14519.5.2.1.290018009822688313704261576268270809186 | MR | Ph1/3D Ax VIBRANT Mph Contrast | 256 | 136.0 | BIA=absent, IdRemoved=YES, priv=204 | breast MR STIR + DCE phase 1 + CT chest-abdomen-pelvis |
| BR-05 | CMB-BRCA | MSB-07863 | n/a/O | 1960-02-20 | 1.3.6.1.4.1.14519.5.2.1.253378065209369186316289882849664271343 | 1.3.6.1.4.1.14519.5.2.1.13128581328072645760787522095632373905 | CT | ENHANCED | 130 | 68.8 | BIA=absent, IdRemoved=YES, priv=121 | breast MR STIR + DCE phase 1 + CT chest-abdomen-pelvis |

### B Lung NSCLC: 7 source patients, 18 series, 1.30 GB

| Slot | Collection | PatientID | Age/sex (source) | StudyDate (source) | StudyInstanceUID | SeriesInstanceUID | Mod | SeriesDescription | Images | MB | Header check | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LU-01 | Lung-PET-CT-Dx | Lung_Dx-A0166 | 064Y/F | 2010-07-21 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.123943627505953940638225177128 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.306347497946607687703883357991 | CT | CT lung  3.0  B70f | 116 | 61.2 | BIA=absent, IdRemoved=YES, priv=14 | adenocarcinoma (A prefix); CT lung 3 mm + PET WB (China) |
| LU-01 | Lung-PET-CT-Dx | Lung_Dx-A0166 | 064Y/F | 2010-07-21 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.123943627505953940638225177128 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.226901752069119903728752256048 | PT | PET WB Corrected | 171 | 14.4 | BIA=absent, IdRemoved=YES, priv=6 | adenocarcinoma (A prefix); CT lung 3 mm + PET WB (China) |
| LU-02 | Lung-PET-CT-Dx | Lung_Dx-A0167 | 049Y/F | 2010-09-08 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.278683840104150114237417093539 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.359821213786510431287657873278 | CT | Thorax  1.0  B31f | 348 | 183.7 | BIA=absent, IdRemoved=YES, priv=14 | adenocarcinoma; CT thorax 1 mm soft tissue + PET WB (China) |
| LU-02 | Lung-PET-CT-Dx | Lung_Dx-A0167 | 049Y/F | 2010-09-08 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.278683840104150114237417093539 | 1.3.6.1.4.1.14519.5.2.1.6655.2359.937028802602237888558910984814 | PT | PET WB Corrected | 243 | 20.5 | BIA=absent, IdRemoved=YES, priv=6 | adenocarcinoma; CT thorax 1 mm soft tissue + PET WB (China) |
| LU-03 | NSCLC Radiogenomics | AMC-003 | 070Y/F | 1995-02-22 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.321485753849766493748670100343 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.273321321773433141847217168170 | CT | THORAX LUNG 2MM | 284 | 149.8 | BIA=absent, IdRemoved=YES, priv=12 | diagnostic CT thorax + PET-CT (CT + PET) |
| LU-03 | NSCLC Radiogenomics | AMC-003 | 070Y/F | 1995-03-21 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.370949726814943009788058836710 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.171727643865200403165802871787 | CT | CTAC | 263 | 138.7 | BIA=absent, IdRemoved=YES, priv=15 | diagnostic CT thorax + PET-CT (CT + PET) |
| LU-03 | NSCLC Radiogenomics | AMC-003 | 070Y/F | 1995-03-21 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.370949726814943009788058836710 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.239170050903449705007919719283 | PT | WB MAC P690 | 263 | 20.4 | BIA=absent, IdRemoved=YES, priv=11 | diagnostic CT thorax + PET-CT (CT + PET) |
| LU-04 | CPTAC-LUAD | C3L-03717 | n/a/F | 2010-05-30 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.281889968596503110419195722915 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.671795264090307480092408242633 | CT | THORAX  3.0 B41 Soft Tissue | 111 | 58.6 | BIA=absent, IdRemoved=YES, priv=17 | CT thorax soft + lung kernel; PET-CT skull to thigh (face check) |
| LU-04 | CPTAC-LUAD | C3L-03717 | n/a/F | 2010-05-30 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.281889968596503110419195722915 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.179042670650173689920449824438 | CT | THORAX  3.0  B70f LUNG | 111 | 58.6 | BIA=absent, IdRemoved=YES, priv=17 | CT thorax soft + lung kernel; PET-CT skull to thigh (face check) |
| LU-04 | CPTAC-LUAD | C3L-03717 | 054Y/F | 2010-02-04 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.110278990254243185390368932801 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.101839196455054321363367605040 | CT | CT BODY | 254 | 134.3 | BIA=absent, IdRemoved=YES, priv=109 | CT thorax soft + lung kernel; PET-CT skull to thigh (face check) |
| LU-04 | CPTAC-LUAD | C3L-03717 | 054Y/F | 2010-02-04 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.110278990254243185390368932801 | 1.3.6.1.4.1.14519.5.2.1.4320.5885.187939005020729072620603626461 | PT | 3D BODY AC | 254 | 10.0 | BIA=absent, IdRemoved=YES, priv=147 | CT thorax soft + lung kernel; PET-CT skull to thigh (face check) |
| LU-05 | TCGA-LUAD | TCGA-17-Z053 | 070Y/M | 1986-05-23 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.202618697820572701792835874057 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.332002723476583484085948161666 | CT | CHEST ROUTINE  5.0  B20f | 61 | 32.2 | BIA=NO, IdRemoved=YES, priv=21 | CT chest routine (2 kernels) + PET-CT |
| LU-05 | TCGA-LUAD | TCGA-17-Z053 | 070Y/M | 1986-05-23 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.202618697820572701792835874057 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.390781160863053487650899552351 | CT | CHEST ROUTINE  5.0  B60f | 58 | 30.6 | BIA=NO, IdRemoved=YES, priv=17 | CT chest routine (2 kernels) + PET-CT |
| LU-05 | TCGA-LUAD | TCGA-17-Z053 | 070Y/M | 1986-09-19 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.271808960320077551697919992033 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.282617070529060301401540230240 | CT | Abd.CT 5.0 B30s | 356 | 187.8 | BIA=NO, IdRemoved=YES, priv=17 | CT chest routine (2 kernels) + PET-CT |
| LU-05 | TCGA-LUAD | TCGA-17-Z053 | 070Y/M | 1986-09-19 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.271808960320077551697919992033 | 1.3.6.1.4.1.14519.5.2.1.7777.9002.329793444034925460865246705358 | PT | PET WB | 355 | 12.8 | BIA=NO, IdRemoved=YES, priv=12 | CT chest routine (2 kernels) + PET-CT |
| LU-06 | LIDC-IDRI | LIDC-IDRI-0001 | n/a/n/a | 2000-01-01 | 1.3.6.1.4.1.14519.5.2.1.6279.6001.298806137288633453246975630178 | 1.3.6.1.4.1.14519.5.2.1.6279.6001.179049373636438705059720603192 | CT | None | 133 | 70.0 | BIA=absent, IdRemoved=YES, priv=3 | CT chest only (nodule case) |
| LU-R1 reserve | NSCLC Radiogenomics | R01-001 | 078Y/F | 1990-10-17 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.515026324580023859840874044295 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.164951610473301901732855875499 | CT | CT Images | 205 | 108.0 | BIA=absent, IdRemoved=YES, priv=4 | reserve: PET-CT |
| LU-R1 reserve | NSCLC Radiogenomics | R01-001 | 078Y/F | 1990-10-17 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.515026324580023859840874044295 | 1.3.6.1.4.1.14519.5.2.1.4334.1501.178204039327031545530855872090 | PT | PET_BODY_CTAC | 204 | 7.4 | BIA=absent, IdRemoved=YES, priv=4 | reserve: PET-CT |

### C Cervix: 4 source patients, 12 series, 0.38 GB

| Slot | Collection | PatientID | Age/sex (source) | StudyDate (source) | StudyInstanceUID | SeriesInstanceUID | Mod | SeriesDescription | Images | MB | Header check | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CX-01 | TCGA-CESC | TCGA-VS-A8EB | n/a/F | 2004-05-05 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.138433740004929571174776420151 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.619064565773374397139264312004 | MR | SAG T2 | 30 | 15.9 | BIA=absent, IdRemoved=YES, priv=54 | MR pelvis sag T2, ax T2 3 mm, ax T1 |
| CX-01 | TCGA-CESC | TCGA-VS-A8EB | n/a/F | 2004-05-05 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.138433740004929571174776420151 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.658390582597899341719337128517 | MR | AXI T2 3mm HR | 32 | 21.4 | BIA=absent, IdRemoved=YES, priv=54 | MR pelvis sag T2, ax T2 3 mm, ax T1 |
| CX-01 | TCGA-CESC | TCGA-VS-A8EB | n/a/F | 2004-05-05 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.138433740004929571174776420151 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.336021808554888695201022910492 | MR | AXI T1 5mm | 45 | 69.9 | BIA=absent, IdRemoved=YES, priv=54 | MR pelvis sag T2, ax T2 3 mm, ax T1 |
| CX-02 | TCGA-CESC | TCGA-VS-A8EG | 036Y/F | 2005-05-01 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.174495913735224729853904842299 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.121131259519940900711834612890 | MR | AX T2 FRFSE | 60 | 31.8 | BIA=absent, IdRemoved=YES, priv=192 | MR pelvis ax T2, sag T2 |
| CX-02 | TCGA-CESC | TCGA-VS-A8EG | 036Y/F | 2005-05-01 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.174495913735224729853904842299 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.142936626424478151296049116871 | MR | SAG T2 FRFSE | 30 | 15.9 | BIA=absent, IdRemoved=YES, priv=192 | MR pelvis ax T2, sag T2 |
| CX-03 | TCGA-CESC | TCGA-VS-A8EH | 056Y/F | 2006-04-10 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.624111080601803447061323803190 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.271125206506988143963552262668 | MR | AX T2 FRFSE | 55 | 29.2 | BIA=absent, IdRemoved=YES, priv=192 | MR pelvis ax T2, sag T2, DWI b800 |
| CX-03 | TCGA-CESC | TCGA-VS-A8EH | 056Y/F | 2006-04-10 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.624111080601803447061323803190 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.138493966832366180383338541857 | MR | SAG T2 FRFSE | 30 | 15.9 | BIA=absent, IdRemoved=YES, priv=192 | MR pelvis ax T2, sag T2, DWI b800 |
| CX-03 | TCGA-CESC | TCGA-VS-A8EH | 056Y/F | 2006-04-10 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.624111080601803447061323803190 | 1.3.6.1.4.1.14519.5.2.1.6354.4022.115707171012444336626752486507 | MR | Ax DWI  b800 | 64 | 8.8 | BIA=absent, IdRemoved=YES, priv=192 | MR pelvis ax T2, sag T2, DWI b800 |
| CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | 041Y/F | 2005-06-10 | 1.3.6.1.4.1.14519.5.2.1.138896841469811825861682738735853817707 | 1.3.6.1.4.1.14519.5.2.1.319364372935035748697625768741573857103 | CT | CT 2.5MM STD | 295 | 155.6 | BIA=absent, IdRemoved=YES, priv=3 | PET-CT (CT + PET) + MR sag T2, ax T2; stage IB2-IVA (face check on PET-CT) |
| CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | 041Y/F | 2005-06-10 | 1.3.6.1.4.1.14519.5.2.1.138896841469811825861682738735853817707 | 1.3.6.1.4.1.14519.5.2.1.315077523559674293758223337866925186907 | PT | FDG 3D SUV OSEM | 230 | 8.4 | BIA=absent, IdRemoved=YES, priv=3 | PET-CT (CT + PET) + MR sag T2, ax T2; stage IB2-IVA (face check on PET-CT) |
| CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | 041Y/F | 2005-06-10 | 1.3.6.1.4.1.14519.5.2.1.208429535251869144811895672844923329927 | 1.3.6.1.4.1.14519.5.2.1.40195598971044314651886312758228421927 | MR | SAG T2 | 30 | 4.0 | BIA=absent, IdRemoved=YES, priv=4 | PET-CT (CT + PET) + MR sag T2, ax T2; stage IB2-IVA (face check on PET-CT) |
| CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | 041Y/F | 2005-06-10 | 1.3.6.1.4.1.14519.5.2.1.208429535251869144811895672844923329927 | 1.3.6.1.4.1.14519.5.2.1.234078588023419285450137167472556934506 | MR | AX T2 | 48 | 6.5 | BIA=absent, IdRemoved=YES, priv=4 | PET-CT (CT + PET) + MR sag T2, ax T2; stage IB2-IVA (face check on PET-CT) |

### D Colorectal: 6 source patients, 14 series, 0.54 GB

| Slot | Collection | PatientID | Age/sex (source) | StudyDate (source) | StudyInstanceUID | SeriesInstanceUID | Mod | SeriesDescription | Images | MB | Header check | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CR-01 | TCGA-READ | TCGA-BM-6198 | 073Y/M | 1991-02-09 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.304030957341830836628192929917 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.275902923659804018150231723509 | MR | t2_haste_sag_p2_mbh_320 | 36 | 7.5 | BIA=absent, IdRemoved=YES, priv=9 | MR rectum sag T2, ax T2, post contrast VIBE + CT abdomen pelvis |
| CR-01 | TCGA-READ | TCGA-BM-6198 | 073Y/M | 1991-02-09 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.304030957341830836628192929917 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.330077288186441027275998687603 | MR | t2_haste__tra_p2_mbh_320 | 44 | 9.1 | BIA=absent, IdRemoved=YES, priv=9 | MR rectum sag T2, ax T2, post contrast VIBE + CT abdomen pelvis |
| CR-01 | TCGA-READ | TCGA-BM-6198 | 073Y/M | 1991-02-09 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.304030957341830836628192929917 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.206096527423871496086339173610 | MR | t1_vibe_fs_tra_p2_320_BH POST | 64 | 10.8 | BIA=absent, IdRemoved=YES, priv=9 | MR rectum sag T2, ax T2, post contrast VIBE + CT abdomen pelvis |
| CR-01 | TCGA-READ | TCGA-BM-6198 | 073Y/M | 1991-03-09 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.329305334176079996095294344892 | 1.3.6.1.4.1.14519.5.2.1.8421.4018.338658711874561200877677046725 | CT | AbdomenPelvis  5.0  B31f | 106 | 55.9 | BIA=absent, IdRemoved=YES, priv=13 | MR rectum sag T2, ax T2, post contrast VIBE + CT abdomen pelvis |
| CR-02 | TCGA-READ | TCGA-CL-4957 | 079Y/F | 1997-08-24 | 1.3.6.1.4.1.14519.5.2.1.3671.4018.495294737070259623679665574402 | 1.3.6.1.4.1.14519.5.2.1.3671.4018.169401970460996734655625885771 | CT | ABD/PEL  5.0  B30f | 79 | 41.7 | BIA=absent, IdRemoved=YES, priv=14 | CT abdomen pelvis axial + coronal |
| CR-02 | TCGA-READ | TCGA-CL-4957 | 079Y/F | 1997-08-24 | 1.3.6.1.4.1.14519.5.2.1.3671.4018.495294737070259623679665574402 | 1.3.6.1.4.1.14519.5.2.1.3671.4018.310318219902633450127700883338 | CT | ABD/PEL  3.0  coronal | 78 | 41.1 | BIA=absent, IdRemoved=YES, priv=13 | CT abdomen pelvis axial + coronal |
| CR-03 | TCGA-COAD | TCGA-AY-4070A | 050Y/F | 1997-12-02 | 1.3.6.1.4.1.14519.5.2.1.8421.4017.314265299318486820415948375829 | 1.3.6.1.4.1.14519.5.2.1.8421.4017.576800355117178104124255800432 | CT | Abdomen_Pelv  5.0  B30f | 87 | 45.9 | BIA=absent, IdRemoved=YES, priv=16 | CT abdomen pelvis, two dates |
| CR-03 | TCGA-COAD | TCGA-AY-4070A | 051Y/F | 1997-12-23 | 1.3.6.1.4.1.14519.5.2.1.8421.4017.206944705526266221852495854472 | 1.3.6.1.4.1.14519.5.2.1.8421.4017.787305079077841007172123472811 | CT | Abd/Pelvis  5.0  B30f | 98 | 51.7 | BIA=absent, IdRemoved=YES, priv=17 | CT abdomen pelvis, two dates |
| CR-04 | Colorectal-Liver-Metastases | CRLM-CT-1002 | 067Y/F | 1992-07-12 | 1.3.6.1.4.1.14519.5.2.1.9203.8273.290195284494875069689894846457 | 1.3.6.1.4.1.14519.5.2.1.9203.8273.455038217313067138673184936282 | CT | None | 178 | 93.8 | BIA=NO, IdRemoved=YES, priv=13 | portal venous CT, liver metastases |
| CR-05 | StageII-Colorectal-CT | StageII-Colorectal-CT-001 | 056Y/M | 2003-09-14 | 1.3.6.1.4.1.14519.5.2.1.307977184265630381302780598936741211625 | 1.3.6.1.4.1.14519.5.2.1.274448496026915359878669995943742612095 | CT | Venous Phase  5.0  B30f | 90 | 47.5 | BIA=absent, IdRemoved=YES, priv=15 | venous phase CT abdomen (China) |
| CR-06 | CMB-CRC | MSB-07414 | 000Y/O | 1959-11-25 | 1.3.6.1.4.1.14519.5.2.1.193715959163749462772504621355846239569 | 1.3.6.1.4.1.14519.5.2.1.22235547254509296594804873769836180829 | MR | T2 AXIAL SFOV (rectum) | 43 | 12.9 | BIA=NO, IdRemoved=YES, priv=84 | MR rectum ax T2 + sag T2 (SFOV) + CT chest + CT abdomen pelvis |
| CR-06 | CMB-CRC | MSB-07414 | 000Y/O | 1959-11-25 | 1.3.6.1.4.1.14519.5.2.1.193715959163749462772504621355846239569 | 1.3.6.1.4.1.14519.5.2.1.135798829041572223187967857947866824460 | MR | T2 SAG SFOV (rectum) | 35 | 10.5 | BIA=NO, IdRemoved=YES, priv=84 | MR rectum ax T2 + sag T2 (SFOV) + CT chest + CT abdomen pelvis |
| CR-06 | CMB-CRC | MSB-07414 | 000Y/O | 1960-03-12 | 1.3.6.1.4.1.14519.5.2.1.6776760914487716476338693147105885138 | 1.3.6.1.4.1.14519.5.2.1.312661079690700362158785873824210500817 | CT | AXIAL ST 3.0 X 3.0 | 116 | 61.2 | BIA=absent, IdRemoved=YES, priv=16 | MR rectum ax T2 + sag T2 (SFOV) + CT chest + CT abdomen pelvis |
| CR-06 | CMB-CRC | MSB-07414 | 000Y/O | 1960-03-12 | 1.3.6.1.4.1.14519.5.2.1.15829162128727219948200747447606851994 | 1.3.6.1.4.1.14519.5.2.1.279488501981467128626160105260850280776 | CT | AXIAL ST 5.0 X 5.0 | 88 | 46.5 | BIA=absent, IdRemoved=YES, priv=16 | MR rectum ax T2 + sag T2 (SFOV) + CT chest + CT abdomen pelvis |

### E Head and neck (stand-in): 4 source patients, 7 series, 0.55 GB

| Slot | Collection | PatientID | Age/sex (source) | StudyDate (source) | StudyInstanceUID | SeriesInstanceUID | Mod | SeriesDescription | Images | MB | Header check | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HN-01 | CPTAC-LUAD | C3N-02948 | 067Y/M | 2011-01-08 | 1.3.6.1.4.1.14519.5.2.1.7085.5885.256579142282257599422502094020 | 1.3.6.1.4.1.14519.5.2.1.7085.5885.265283649568652998885984796148 | CT | NECK  3.0  I31s  3 | 110 | 58.1 | BIA=absent, IdRemoved=YES, priv=15 | CT neck with contrast axial + coronal, PET WB; lung cancer patient; FACE CHECK |
| HN-01 | CPTAC-LUAD | C3N-02948 | 067Y/M | 2011-01-08 | 1.3.6.1.4.1.14519.5.2.1.7085.5885.256579142282257599422502094020 | 1.3.6.1.4.1.14519.5.2.1.7085.5885.762247069614920946855231242756 | CT | CORONAL | 106 | 68.0 | BIA=absent, IdRemoved=YES, priv=15 | CT neck with contrast axial + coronal, PET WB; lung cancer patient; FACE CHECK |
| HN-01 | CPTAC-LUAD | C3N-02948 | 067Y/M | 2011-02-01 | 1.3.6.1.4.1.14519.5.2.1.7085.5885.258975396281385124706979404409 | 1.3.6.1.4.1.14519.5.2.1.7085.5885.340056541303503730469332484198 | PT | PET WB (AC) | 292 | 17.7 | BIA=absent, IdRemoved=YES, priv=11 | CT neck with contrast axial + coronal, PET WB; lung cancer patient; FACE CHECK |
| HN-02 | Mediastinal-Lymph-Node-SEG | case_0256 | n/a/M | 2010-03-07 | 1.3.6.1.4.1.14519.5.2.1.307340746124313499908466317125663440261 | 1.3.6.1.4.1.14519.5.2.1.23846379035204500340958459297466932910 | CT | None | 121 | 63.7 | BIA=absent, IdRemoved=YES, priv=3 | CT labelled NECK with lymphadenopathy; FACE CHECK |
| HN-03 | Mediastinal-Lymph-Node-SEG | case_0849 | n/a/M | 2009-01-13 | 1.3.6.1.4.1.14519.5.2.1.105408442546245727783018480125945221522 | 1.3.6.1.4.1.14519.5.2.1.285110630815678685275642769384221232441 | CT | None | 118 | 62.1 | BIA=absent, IdRemoved=YES, priv=3 | CT labelled NECK with lymphadenopathy; FACE CHECK |
| HN-04 | FDG-PET-CT-Lesions | PETCT_0143bab87a | 084Y/M | 2005-07-17 | 1.3.6.1.4.1.14519.5.2.1.4219.6651.335264930457989722278222033529 | 1.3.6.1.4.1.14519.5.2.1.34396790779504476964035972928166943532 | CT | GK p.v.3 s | 345 | 182.3 | BIA=absent, IdRemoved=YES, priv=21 | whole body PET-CT, defaced release |
| HN-04 | FDG-PET-CT-Lesions | PETCT_0143bab87a | 084Y/M | 2005-07-17 | 1.3.6.1.4.1.14519.5.2.1.4219.6651.335264930457989722278222033529 | 1.3.6.1.4.1.14519.5.2.1.34994113673213434627138532167525494455 | PT | PET corr. | 288 | 93.6 | BIA=absent, IdRemoved=YES, priv=15 | whole body PET-CT, defaced release |

### F CUP: 5 source patients, 9 series, 0.93 GB

| Slot | Collection | PatientID | Age/sex (source) | StudyDate (source) | StudyInstanceUID | SeriesInstanceUID | Mod | SeriesDescription | Images | MB | Header check | Note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CUP-01 | FDG-PET-CT-Lesions | PETCT_01140d52d8 | 061Y/M | 2005-08-13 | 1.3.6.1.4.1.14519.5.2.1.4219.6651.316964892168994707041803056839 | 1.3.6.1.4.1.14519.5.2.1.111876236207536139065956127623181501702 | CT | GK p.v.3 s | 366 | 193.4 | BIA=absent, IdRemoved=YES, priv=22 | whole body PET-CT with contrast CT, defaced release |
| CUP-01 | FDG-PET-CT-Lesions | PETCT_01140d52d8 | 061Y/M | 2005-08-13 | 1.3.6.1.4.1.14519.5.2.1.4219.6651.316964892168994707041803056839 | 1.3.6.1.4.1.14519.5.2.1.212851949757273249879468776364398875276 | PT | PET corr. | 305 | 99.1 | BIA=absent, IdRemoved=YES, priv=15 | whole body PET-CT with contrast CT, defaced release |
| CUP-02 | FDG-PET-CT-Lesions | PETCT_0011f3deaf | 063Y/F | 2003-03-23 | 1.3.6.1.4.1.14519.5.2.1.4219.6651.389860614478618826979455610445 | 1.3.6.1.4.1.14519.5.2.1.239537544060707922869401739533283658263 | CT | GK p.v.3 | 391 | 206.5 | BIA=absent, IdRemoved=YES, priv=22 | whole body PET-CT with contrast CT, defaced release |
| CUP-02 | FDG-PET-CT-Lesions | PETCT_0011f3deaf | 063Y/F | 2003-03-23 | 1.3.6.1.4.1.14519.5.2.1.4219.6651.389860614478618826979455610445 | 1.3.6.1.4.1.14519.5.2.1.250262599227532712559738773326631678839 | PT | PET corr. | 326 | 105.9 | BIA=absent, IdRemoved=YES, priv=15 | whole body PET-CT with contrast CT, defaced release |
| CUP-03 | CMB-LCA | MSB-06720 | 000Y/O | 1960-07-07 | 1.3.6.1.4.1.14519.5.2.1.1.32149424009306477320836124242982096081 | 1.3.6.1.4.1.14519.5.2.1.1.29527738786432406266587619077510624166 | CT | CHEST ST Body Axial 3.0  CE | 118 | 62.3 | BIA=absent, IdRemoved=YES, priv=3 | CT chest-abdomen-pelvis with contrast (chest + abdomen series) |
| CUP-03 | CMB-LCA | MSB-06720 | 000Y/O | 1960-07-07 | 1.3.6.1.4.1.14519.5.2.1.1.32149424009306477320836124242982096081 | 1.3.6.1.4.1.14519.5.2.1.1.99924087997900740903375384971900443824 | CT | ABD ST Body Axial 3.0  CE | 126 | 66.5 | BIA=absent, IdRemoved=YES, priv=3 | CT chest-abdomen-pelvis with contrast (chest + abdomen series) |
| CUP-04 | CPTAC-PDA | C3L-04480 | 064Y/M | 2005-05-28 | 1.3.6.1.4.1.14519.5.2.1.1078.3273.167979511297133459052931282918 | 1.3.6.1.4.1.14519.5.2.1.1078.3273.116096825250924485225275072755 | CT | 5 X 2.5 AXIAL ABDOMEN | 194 | 102.7 | BIA=absent, IdRemoved=YES, priv=122 | CT chest-abdomen-pelvis enhanced (abdomen + chest series) |
| CUP-04 | CPTAC-PDA | C3L-04480 | 064Y/M | 2005-05-28 | 1.3.6.1.4.1.14519.5.2.1.1078.3273.167979511297133459052931282918 | 1.3.6.1.4.1.14519.5.2.1.1078.3273.289058566670133314319890183759 | CT | CHEST SOFT TISSUE | 74 | 39.1 | BIA=absent, IdRemoved=YES, priv=31 | CT chest-abdomen-pelvis enhanced (abdomen + chest series) |
| CUP-05 | Mediastinal-Lymph-Node-SEG | case_0005 | n/a/F | 2011-11-08 | 1.3.6.1.4.1.14519.5.2.1.108398914175064278879584112772695642903 | 1.3.6.1.4.1.14519.5.2.1.297586689304226835368002003985734825718 | CT | None | 101 | 53.2 | BIA=absent, IdRemoved=YES, priv=3 | CT chest-abdomen-pelvis with lymphadenopathy |

Notes on the picks:

- Breast: BR-01 and BR-02 are digital mammograms only (CMMD; the D1 series are two views of one side, the D2 series are four views bilateral). BR-03 (TCGA-BRCA) has diagnostic mammograms and a breast MRI (T2 and post contrast VIBRANT). BR-04 has bilateral diagnostic digital mammograms plus a CT chest. BR-05 has breast MRI (STIR plus one dynamic post contrast phase) plus a contrast CT chest-abdomen-pelvis. One BR-03 mammogram series is MONOCHROME1 (inverted LUT); any DICOM viewer handles it, but check the display once.
- Lung: LU-01 and LU-02 are adenocarcinoma cases from Lung-PET-CT-Dx (patient prefix A) with CT thorax and whole body PET from the same visit. LU-03 has a separate diagnostic CT thorax and a PET-CT. LU-04 has a CT thorax in two kernels and a skull to thigh PET-CT (FACE CHECK). LU-05 has a routine contrast CT chest in two kernels and a PET-CT. LU-06 is CT only (LIDC-IDRI, nodule case; the collection also offers a diagnosis spreadsheet for some patients, not verified for patient 0001). LU-R1 is a reserve PET-CT.
- Cervix: CX-01 to CX-03 are pelvic MRI from TCGA-CESC (sagittal and axial T2, plus T1 or DWI). CX-04 adds a PET-CT and MRI from CC-Tumor-Heterogeneity (stage IB2 to IVA, before chemoradiation). The CX-04 PET-CT protocol says "FDG 3D BU CERVICAL", 295 CT slices at 2.5 mm, so it probably runs from the thighs to the skull base: FACE CHECK.
- Colorectal: CR-01 is the best rectal case (rectal MRI with T2 sagittal, T2 axial, post contrast VIBE, plus a contrast CT abdomen pelvis). CR-06 (CMB-CRC) is the other full rectal workup: small field of view rectal T2 in two planes plus CT chest and CT abdomen pelvis. CR-02, CR-03 and CR-05 are CT abdomen pelvis cases, CR-04 is a portal venous CT with liver metastases.
- Head and neck stand-ins: HN-01 is a real contrast CT neck (axial 3 mm plus coronal reformat) and a whole body PET from a lung cancer patient in CPTAC-LUAD. HN-02 and HN-03 are CT series labelled NECK (99 to 126 slices, likely neck plus upper chest) from patients with lymphadenopathy; the collection includes head and neck cancer patients but the per-case diagnosis is not in the DICOM, so "not verified". HN-04 is a defaced whole body PET-CT. All four are FACE CHECK items, and all must be shown as stand-ins.
- CUP: CUP-01 and CUP-02 are defaced whole body FDG PET-CT with contrast CT (German descriptions "GK p.v." = whole body portal venous). CUP-03 is a contrast CT chest-abdomen-pelvis in two series. CUP-04 is a contrast CT chest-abdomen-pelvis from a pancreatic cancer patient. CUP-05 is a CT chest-abdomen-pelvis with lymphadenopathy. For a CUP story the "unknown primary" is written by us, the images only need to show plausible disease.

## 3. Download commands

API check made in this session: GET getImage?SeriesInstanceUID=... on a 106 slice CT returned HTTP 200, content type application/octet-stream, a zip of about 28 MB for 56 MB of DICOM. The server ignores HTTP Range headers (my 1 KB range probe received the whole file), so there is no resume: on failure delete the zip and run the command again. Use -m 3600 for the big series; the longest here is about 210 MB. The v4 variant https://nbia.cancerimagingarchive.net/nbia-api/services/v4/getImage?NewFileNames=Yes&SeriesInstanceUID=... also works and names the files by instance number; v4 getImageWithMD5Hash?SeriesInstanceUID=... adds an md5hashes.csv inside the zip (not tested here).

Ready to run script (generated from picks.json, one curl per series, skips zips already present, counts .dcm files after each download): /tmp/claude-1003/-home-bharath-tangella-vaidyx/1b6283bf-9372-4a28-8719-11ae9768fdee/scratchpad/pacs/download_tcia.sh

Plain list of the exact curl commands (same content): /tmp/claude-1003/-home-bharath-tangella-vaidyx/1b6283bf-9372-4a28-8719-11ae9768fdee/scratchpad/pacs/curl_commands.txt

```bash
B=https://services.cancerimagingarchive.net/nbia-api/services/v1
# BR-01 | CMMD | D1-0001 | MG | None | 2 images | 8.8 MB
curl -sS -L -m 3600 --retry 3 -o "BR-01__CMMD__D1-0001__MG__16970244.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.1239.1759.623006463861567934606116970244"
# BR-02 | CMMD | D2-0140 | MG | None | 4 images | 17.6 MB
curl -sS -L -m 3600 --retry 3 -o "BR-02__CMMD__D2-0140__MG__81244160.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.1239.1759.115060983843511037348481244160"
# BR-03 | TCGA-BRCA | TCGA-AO-A0JI | MG | DIAG MAMMOGRAM U | 2 images | 17.6 MB
curl -sS -L -m 3600 --retry 3 -o "BR-03__TCGA-BRCA__TCGA-AO-A0JI__MG__59792020.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.9203.4002.997993139263721918674259792020"
# BR-03 | TCGA-BRCA | TCGA-AO-A0JI | MG | DIAG MAMMOGRAM U | 2 images | 17.6 MB
curl -sS -L -m 3600 --retry 3 -o "BR-03__TCGA-BRCA__TCGA-AO-A0JI__MG__50353099.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.9203.4002.819947422704003839421250353099"
# BR-03 | TCGA-BRCA | TCGA-AO-A0JI | MR | T2 left breast | 46 images | 6.3 MB
curl -sS -L -m 3600 --retry 3 -o "BR-03__TCGA-BRCA__TCGA-AO-A0JI__MR__06368352.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.9203.4002.112501477437352839202306368352"
# BR-03 | TCGA-BRCA | TCGA-AO-A0JI | MR | Ax Vibrant post | 62 images | 32.8 MB
curl -sS -L -m 3600 --retry 3 -o "BR-03__TCGA-BRCA__TCGA-AO-A0JI__MR__38512275.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.9203.4002.179993109981592527027438512275"
# BR-04 | CMB-BRCA | MSB-08876 | MG | Diagnostic digital bilateral mammo | 4 images | 58.7 MB
curl -sS -L -m 3600 --retry 3 -o "BR-04__CMB-BRCA__MSB-08876__MG__67871841.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.207776098961005429284467902411167871841"
# BR-04 | CMB-BRCA | MSB-08876 | CT | 2.5MM STD 50% ASIR | 117 images | 61.9 MB
curl -sS -L -m 3600 --retry 3 -o "BR-04__CMB-BRCA__MSB-08876__CT__73369383.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.154688781059619045804962302064173369383"
# BR-05 | CMB-BRCA | MSB-07863 | MR | Ax T2 FSE STIR | 54 images | 113.6 MB
curl -sS -L -m 3600 --retry 3 -o "BR-05__CMB-BRCA__MSB-07863__MR__20497758.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.155063585747407232218562393551620497758"
# BR-05 | CMB-BRCA | MSB-07863 | MR | Ph1/3D Ax VIBRANT Mph Contrast | 256 images | 136.0 MB
curl -sS -L -m 3600 --retry 3 -o "BR-05__CMB-BRCA__MSB-07863__MR__70809186.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.290018009822688313704261576268270809186"
# BR-05 | CMB-BRCA | MSB-07863 | CT | ENHANCED | 130 images | 68.8 MB
curl -sS -L -m 3600 --retry 3 -o "BR-05__CMB-BRCA__MSB-07863__CT__32373905.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.13128581328072645760787522095632373905"
# LU-01 | Lung-PET-CT-Dx | Lung_Dx-A0166 | CT | CT lung  3.0  B70f | 116 images | 61.2 MB
curl -sS -L -m 3600 --retry 3 -o "LU-01__Lung-PET-CT-Dx__Lung_Dx-A0166__CT__83357991.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6655.2359.306347497946607687703883357991"
# LU-01 | Lung-PET-CT-Dx | Lung_Dx-A0166 | PT | PET WB Corrected | 171 images | 14.4 MB
curl -sS -L -m 3600 --retry 3 -o "LU-01__Lung-PET-CT-Dx__Lung_Dx-A0166__PT__52256048.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6655.2359.226901752069119903728752256048"
# LU-02 | Lung-PET-CT-Dx | Lung_Dx-A0167 | CT | Thorax  1.0  B31f | 348 images | 183.7 MB
curl -sS -L -m 3600 --retry 3 -o "LU-02__Lung-PET-CT-Dx__Lung_Dx-A0167__CT__57873278.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6655.2359.359821213786510431287657873278"
# LU-02 | Lung-PET-CT-Dx | Lung_Dx-A0167 | PT | PET WB Corrected | 243 images | 20.5 MB
curl -sS -L -m 3600 --retry 3 -o "LU-02__Lung-PET-CT-Dx__Lung_Dx-A0167__PT__10984814.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6655.2359.937028802602237888558910984814"
# LU-03 | NSCLC Radiogenomics | AMC-003 | CT | THORAX LUNG 2MM | 284 images | 149.8 MB
curl -sS -L -m 3600 --retry 3 -o "LU-03__NSCLC_Radiogenomics__AMC-003__CT__17168170.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4334.1501.273321321773433141847217168170"
# LU-03 | NSCLC Radiogenomics | AMC-003 | CT | CTAC | 263 images | 138.7 MB
curl -sS -L -m 3600 --retry 3 -o "LU-03__NSCLC_Radiogenomics__AMC-003__CT__02871787.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4334.1501.171727643865200403165802871787"
# LU-03 | NSCLC Radiogenomics | AMC-003 | PT | WB MAC P690 | 263 images | 20.4 MB
curl -sS -L -m 3600 --retry 3 -o "LU-03__NSCLC_Radiogenomics__AMC-003__PT__19719283.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4334.1501.239170050903449705007919719283"
# LU-04 | CPTAC-LUAD | C3L-03717 | CT | THORAX  3.0 B41 Soft Tissue | 111 images | 58.6 MB
curl -sS -L -m 3600 --retry 3 -o "LU-04__CPTAC-LUAD__C3L-03717__CT__08242633.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4320.5885.671795264090307480092408242633"
# LU-04 | CPTAC-LUAD | C3L-03717 | CT | THORAX  3.0  B70f LUNG | 111 images | 58.6 MB
curl -sS -L -m 3600 --retry 3 -o "LU-04__CPTAC-LUAD__C3L-03717__CT__49824438.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4320.5885.179042670650173689920449824438"
# LU-04 | CPTAC-LUAD | C3L-03717 | CT | CT BODY | 254 images | 134.3 MB
curl -sS -L -m 3600 --retry 3 -o "LU-04__CPTAC-LUAD__C3L-03717__CT__67605040.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4320.5885.101839196455054321363367605040"
# LU-04 | CPTAC-LUAD | C3L-03717 | PT | 3D BODY AC | 254 images | 10.0 MB
curl -sS -L -m 3600 --retry 3 -o "LU-04__CPTAC-LUAD__C3L-03717__PT__03626461.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4320.5885.187939005020729072620603626461"
# LU-05 | TCGA-LUAD | TCGA-17-Z053 | CT | CHEST ROUTINE  5.0  B20f | 61 images | 32.2 MB
curl -sS -L -m 3600 --retry 3 -o "LU-05__TCGA-LUAD__TCGA-17-Z053__CT__48161666.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.7777.9002.332002723476583484085948161666"
# LU-05 | TCGA-LUAD | TCGA-17-Z053 | CT | CHEST ROUTINE  5.0  B60f | 58 images | 30.6 MB
curl -sS -L -m 3600 --retry 3 -o "LU-05__TCGA-LUAD__TCGA-17-Z053__CT__99552351.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.7777.9002.390781160863053487650899552351"
# LU-05 | TCGA-LUAD | TCGA-17-Z053 | CT | Abd.CT 5.0 B30s | 356 images | 187.8 MB
curl -sS -L -m 3600 --retry 3 -o "LU-05__TCGA-LUAD__TCGA-17-Z053__CT__40230240.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.7777.9002.282617070529060301401540230240"
# LU-05 | TCGA-LUAD | TCGA-17-Z053 | PT | PET WB | 355 images | 12.8 MB
curl -sS -L -m 3600 --retry 3 -o "LU-05__TCGA-LUAD__TCGA-17-Z053__PT__46705358.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.7777.9002.329793444034925460865246705358"
# LU-06 | LIDC-IDRI | LIDC-IDRI-0001 | CT | None | 133 images | 70.0 MB
curl -sS -L -m 3600 --retry 3 -o "LU-06__LIDC-IDRI__LIDC-IDRI-0001__CT__20603192.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6279.6001.179049373636438705059720603192"
# LU-R1 reserve | NSCLC Radiogenomics | R01-001 | CT | CT Images | 205 images | 108.0 MB
curl -sS -L -m 3600 --retry 3 -o "LU-R1_reserve__NSCLC_Radiogenomics__R01-001__CT__55875499.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4334.1501.164951610473301901732855875499"
# LU-R1 reserve | NSCLC Radiogenomics | R01-001 | PT | PET_BODY_CTAC | 204 images | 7.4 MB
curl -sS -L -m 3600 --retry 3 -o "LU-R1_reserve__NSCLC_Radiogenomics__R01-001__PT__55872090.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.4334.1501.178204039327031545530855872090"
# CX-01 | TCGA-CESC | TCGA-VS-A8EB | MR | SAG T2 | 30 images | 15.9 MB
curl -sS -L -m 3600 --retry 3 -o "CX-01__TCGA-CESC__TCGA-VS-A8EB__MR__64312004.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.619064565773374397139264312004"
# CX-01 | TCGA-CESC | TCGA-VS-A8EB | MR | AXI T2 3mm HR | 32 images | 21.4 MB
curl -sS -L -m 3600 --retry 3 -o "CX-01__TCGA-CESC__TCGA-VS-A8EB__MR__37128517.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.658390582597899341719337128517"
# CX-01 | TCGA-CESC | TCGA-VS-A8EB | MR | AXI T1 5mm | 45 images | 69.9 MB
curl -sS -L -m 3600 --retry 3 -o "CX-01__TCGA-CESC__TCGA-VS-A8EB__MR__22910492.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.336021808554888695201022910492"
# CX-02 | TCGA-CESC | TCGA-VS-A8EG | MR | AX T2 FRFSE | 60 images | 31.8 MB
curl -sS -L -m 3600 --retry 3 -o "CX-02__TCGA-CESC__TCGA-VS-A8EG__MR__34612890.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.121131259519940900711834612890"
# CX-02 | TCGA-CESC | TCGA-VS-A8EG | MR | SAG T2 FRFSE | 30 images | 15.9 MB
curl -sS -L -m 3600 --retry 3 -o "CX-02__TCGA-CESC__TCGA-VS-A8EG__MR__49116871.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.142936626424478151296049116871"
# CX-03 | TCGA-CESC | TCGA-VS-A8EH | MR | AX T2 FRFSE | 55 images | 29.2 MB
curl -sS -L -m 3600 --retry 3 -o "CX-03__TCGA-CESC__TCGA-VS-A8EH__MR__52262668.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.271125206506988143963552262668"
# CX-03 | TCGA-CESC | TCGA-VS-A8EH | MR | SAG T2 FRFSE | 30 images | 15.9 MB
curl -sS -L -m 3600 --retry 3 -o "CX-03__TCGA-CESC__TCGA-VS-A8EH__MR__38541857.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.138493966832366180383338541857"
# CX-03 | TCGA-CESC | TCGA-VS-A8EH | MR | Ax DWI  b800 | 64 images | 8.8 MB
curl -sS -L -m 3600 --retry 3 -o "CX-03__TCGA-CESC__TCGA-VS-A8EH__MR__52486507.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.6354.4022.115707171012444336626752486507"
# CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | CT | CT 2.5MM STD | 295 images | 155.6 MB
curl -sS -L -m 3600 --retry 3 -o "CX-04__CC-Tumor-Heterogeneity__CCTH-A02__CT__73857103.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.319364372935035748697625768741573857103"
# CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | PT | FDG 3D SUV OSEM | 230 images | 8.4 MB
curl -sS -L -m 3600 --retry 3 -o "CX-04__CC-Tumor-Heterogeneity__CCTH-A02__PT__25186907.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.315077523559674293758223337866925186907"
# CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | MR | SAG T2 | 30 images | 4.0 MB
curl -sS -L -m 3600 --retry 3 -o "CX-04__CC-Tumor-Heterogeneity__CCTH-A02__MR__28421927.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.40195598971044314651886312758228421927"
# CX-04 | CC-Tumor-Heterogeneity | CCTH-A02 | MR | AX T2 | 48 images | 6.5 MB
curl -sS -L -m 3600 --retry 3 -o "CX-04__CC-Tumor-Heterogeneity__CCTH-A02__MR__56934506.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.234078588023419285450137167472556934506"
# CR-01 | TCGA-READ | TCGA-BM-6198 | MR | t2_haste_sag_p2_mbh_320 | 36 images | 7.5 MB
curl -sS -L -m 3600 --retry 3 -o "CR-01__TCGA-READ__TCGA-BM-6198__MR__31723509.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.8421.4018.275902923659804018150231723509"
# CR-01 | TCGA-READ | TCGA-BM-6198 | MR | t2_haste__tra_p2_mbh_320 | 44 images | 9.1 MB
curl -sS -L -m 3600 --retry 3 -o "CR-01__TCGA-READ__TCGA-BM-6198__MR__98687603.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.8421.4018.330077288186441027275998687603"
# CR-01 | TCGA-READ | TCGA-BM-6198 | MR | t1_vibe_fs_tra_p2_320_BH POST | 64 images | 10.8 MB
curl -sS -L -m 3600 --retry 3 -o "CR-01__TCGA-READ__TCGA-BM-6198__MR__39173610.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.8421.4018.206096527423871496086339173610"
# CR-01 | TCGA-READ | TCGA-BM-6198 | CT | AbdomenPelvis  5.0  B31f | 106 images | 55.9 MB
curl -sS -L -m 3600 --retry 3 -o "CR-01__TCGA-READ__TCGA-BM-6198__CT__77046725.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.8421.4018.338658711874561200877677046725"
# CR-02 | TCGA-READ | TCGA-CL-4957 | CT | ABD/PEL  5.0  B30f | 79 images | 41.7 MB
curl -sS -L -m 3600 --retry 3 -o "CR-02__TCGA-READ__TCGA-CL-4957__CT__25885771.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.3671.4018.169401970460996734655625885771"
# CR-02 | TCGA-READ | TCGA-CL-4957 | CT | ABD/PEL  3.0  coronal | 78 images | 41.1 MB
curl -sS -L -m 3600 --retry 3 -o "CR-02__TCGA-READ__TCGA-CL-4957__CT__00883338.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.3671.4018.310318219902633450127700883338"
# CR-03 | TCGA-COAD | TCGA-AY-4070A | CT | Abdomen_Pelv  5.0  B30f | 87 images | 45.9 MB
curl -sS -L -m 3600 --retry 3 -o "CR-03__TCGA-COAD__TCGA-AY-4070A__CT__55800432.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.8421.4017.576800355117178104124255800432"
# CR-03 | TCGA-COAD | TCGA-AY-4070A | CT | Abd/Pelvis  5.0  B30f | 98 images | 51.7 MB
curl -sS -L -m 3600 --retry 3 -o "CR-03__TCGA-COAD__TCGA-AY-4070A__CT__23472811.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.8421.4017.787305079077841007172123472811"
# CR-04 | Colorectal-Liver-Metastases | CRLM-CT-1002 | CT | None | 178 images | 93.8 MB
curl -sS -L -m 3600 --retry 3 -o "CR-04__Colorectal-Liver-Metastases__CRLM-CT-1002__CT__84936282.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.9203.8273.455038217313067138673184936282"
# CR-05 | StageII-Colorectal-CT | StageII-Colorectal-CT-001 | CT | Venous Phase  5.0  B30f | 90 images | 47.5 MB
curl -sS -L -m 3600 --retry 3 -o "CR-05__StageII-Colorectal-CT__StageII-Colorectal-CT-001__CT__42612095.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.274448496026915359878669995943742612095"
# CR-06 | CMB-CRC | MSB-07414 | MR | T2 AXIAL SFOV (rectum) | 43 images | 12.9 MB
curl -sS -L -m 3600 --retry 3 -o "CR-06__CMB-CRC__MSB-07414__MR__36180829.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.22235547254509296594804873769836180829"
# CR-06 | CMB-CRC | MSB-07414 | MR | T2 SAG SFOV (rectum) | 35 images | 10.5 MB
curl -sS -L -m 3600 --retry 3 -o "CR-06__CMB-CRC__MSB-07414__MR__66824460.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.135798829041572223187967857947866824460"
# CR-06 | CMB-CRC | MSB-07414 | CT | AXIAL ST 3.0 X 3.0 | 116 images | 61.2 MB
curl -sS -L -m 3600 --retry 3 -o "CR-06__CMB-CRC__MSB-07414__CT__10500817.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.312661079690700362158785873824210500817"
# CR-06 | CMB-CRC | MSB-07414 | CT | AXIAL ST 5.0 X 5.0 | 88 images | 46.5 MB
curl -sS -L -m 3600 --retry 3 -o "CR-06__CMB-CRC__MSB-07414__CT__50280776.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.279488501981467128626160105260850280776"
# HN-01 | CPTAC-LUAD | C3N-02948 | CT | NECK  3.0  I31s  3 | 110 images | 58.1 MB
curl -sS -L -m 3600 --retry 3 -o "HN-01__CPTAC-LUAD__C3N-02948__CT__84796148.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.7085.5885.265283649568652998885984796148"
# HN-01 | CPTAC-LUAD | C3N-02948 | CT | CORONAL | 106 images | 68.0 MB
curl -sS -L -m 3600 --retry 3 -o "HN-01__CPTAC-LUAD__C3N-02948__CT__31242756.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.7085.5885.762247069614920946855231242756"
# HN-01 | CPTAC-LUAD | C3N-02948 | PT | PET WB (AC) | 292 images | 17.7 MB
curl -sS -L -m 3600 --retry 3 -o "HN-01__CPTAC-LUAD__C3N-02948__PT__32484198.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.7085.5885.340056541303503730469332484198"
# HN-02 | Mediastinal-Lymph-Node-SEG | case_0256 | CT | None | 121 images | 63.7 MB
curl -sS -L -m 3600 --retry 3 -o "HN-02__Mediastinal-Lymph-Node-SEG__case_0256__CT__66932910.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.23846379035204500340958459297466932910"
# HN-03 | Mediastinal-Lymph-Node-SEG | case_0849 | CT | None | 118 images | 62.1 MB
curl -sS -L -m 3600 --retry 3 -o "HN-03__Mediastinal-Lymph-Node-SEG__case_0849__CT__21232441.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.285110630815678685275642769384221232441"
# HN-04 | FDG-PET-CT-Lesions | PETCT_0143bab87a | CT | GK p.v.3 s | 345 images | 182.3 MB
curl -sS -L -m 3600 --retry 3 -o "HN-04__FDG-PET-CT-Lesions__PETCT_0143bab87a__CT__66943532.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.34396790779504476964035972928166943532"
# HN-04 | FDG-PET-CT-Lesions | PETCT_0143bab87a | PT | PET corr. | 288 images | 93.6 MB
curl -sS -L -m 3600 --retry 3 -o "HN-04__FDG-PET-CT-Lesions__PETCT_0143bab87a__PT__25494455.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.34994113673213434627138532167525494455"
# CUP-01 | FDG-PET-CT-Lesions | PETCT_01140d52d8 | CT | GK p.v.3 s | 366 images | 193.4 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-01__FDG-PET-CT-Lesions__PETCT_01140d52d8__CT__81501702.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.111876236207536139065956127623181501702"
# CUP-01 | FDG-PET-CT-Lesions | PETCT_01140d52d8 | PT | PET corr. | 305 images | 99.1 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-01__FDG-PET-CT-Lesions__PETCT_01140d52d8__PT__98875276.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.212851949757273249879468776364398875276"
# CUP-02 | FDG-PET-CT-Lesions | PETCT_0011f3deaf | CT | GK p.v.3 | 391 images | 206.5 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-02__FDG-PET-CT-Lesions__PETCT_0011f3deaf__CT__83658263.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.239537544060707922869401739533283658263"
# CUP-02 | FDG-PET-CT-Lesions | PETCT_0011f3deaf | PT | PET corr. | 326 images | 105.9 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-02__FDG-PET-CT-Lesions__PETCT_0011f3deaf__PT__31678839.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.250262599227532712559738773326631678839"
# CUP-03 | CMB-LCA | MSB-06720 | CT | CHEST ST Body Axial 3.0  CE | 118 images | 62.3 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-03__CMB-LCA__MSB-06720__CT__10624166.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.1.29527738786432406266587619077510624166"
# CUP-03 | CMB-LCA | MSB-06720 | CT | ABD ST Body Axial 3.0  CE | 126 images | 66.5 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-03__CMB-LCA__MSB-06720__CT__00443824.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.1.99924087997900740903375384971900443824"
# CUP-04 | CPTAC-PDA | C3L-04480 | CT | 5 X 2.5 AXIAL ABDOMEN | 194 images | 102.7 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-04__CPTAC-PDA__C3L-04480__CT__75072755.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.1078.3273.116096825250924485225275072755"
# CUP-04 | CPTAC-PDA | C3L-04480 | CT | CHEST SOFT TISSUE | 74 images | 39.1 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-04__CPTAC-PDA__C3L-04480__CT__90183759.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.1078.3273.289058566670133314319890183759"
# CUP-05 | Mediastinal-Lymph-Node-SEG | case_0005 | CT | None | 101 images | 53.2 MB
curl -sS -L -m 3600 --retry 3 -o "CUP-05__Mediastinal-Lymph-Node-SEG__case_0005__CT__34825718.zip" "$B/getImage?SeriesInstanceUID=1.3.6.1.4.1.14519.5.2.1.297586689304226835368002003985734825718"
```

Download into a fresh empty directory, keep every zip (they are the provenance record), verify each with unzip -t and by counting .dcm files against the image count in the table, then extract into a second directory that only the de-identification script reads. Record the download date, the zip size and its md5sum in the manifest.

## 4. De-identification and QA plan

What TCIA already did: every chosen series has PatientIdentityRemoved (0012,0062) = YES and DeidentificationMethod (0012,0063) = "Per DICOM PS 3.15 AnnexE" (CTP based, some with MIM or dcmjs steps). PatientName equals the TCIA PatientID, birth date is empty, dates are shifted by the submitter, InstitutionName is empty. AccessionNumber is present in TCGA and NSCLC Radiogenomics series but is already a random 16 digit number. PatientAge and PatientSex are present in most series (CMB series carry sex = O and age = 000Y).

What we still do, for every file (pydicom script, run on the extracted copy, writing to a third directory that becomes the PACS import source):

1. Identity: set PatientName and PatientID to the fake Indian persona of the demo slot (one persona per source patient, never reuse a persona across two source patients). Set PatientBirthDate to the persona DOB, PatientSex to the persona sex (keep it consistent with the images: breast and cervix cases female, BR-04 and BR-05 come with sex = O in the header and must be set to F), recompute PatientAge from the DOB and the new StudyDate. Blank OtherPatientIDs, OtherPatientNames, PatientAddress, PatientTelephoneNumbers, PatientComments, EthnicGroup, PatientWeight and PatientSize (or set persona values).
2. Dates and times: pick one offset per source patient so that the earliest chosen study lands on the date the demo story needs (for example 2026-08 to 2026-10), and apply the same offset to StudyDate, SeriesDate, AcquisitionDate, ContentDate, and to the date part of any other DA or DT element (RadiopharmaceuticalStartDateTime in PET, PerformedProcedureStepStartDate, etc.) so intervals inside a patient stay true. Keep the times. CMB dates sit around 1959 to 1961 and TCGA dates around 1986 to 2006 today, so the offset is large; compute it, do not type it.
3. Study and institution: set AccessionNumber to a fake hospital accession, StudyID to a fake value, StudyDescription and SeriesDescription to plain English demo names (keep the original SeriesDescription in the manifest), InstitutionName and InstitutionAddress to the demo hospital, StationName blank, ReferringPhysicianName, PerformingPhysicianName, PhysiciansOfRecord, RequestingPhysician, OperatorsName to demo values or blank. Set InstitutionalDepartmentName if the PACS shows it.
4. Provenance tags that leak the source: TCIA sets ClinicalTrialProtocolID (0012,0020), ClinicalTrialSiteID (0012,0030), ClinicalTrialSubjectID (0012,0040) and ClinicalTrialSponsorName (0012,0010) to the collection name and the TCIA patient ID. Blank them in the files (a header view in the PACS would otherwise show "TCGA-AO-A0JI") and keep the mapping in the manifest instead. Keep DeidentificationMethod and append our own step ("Vaidyx demo relabel 2026-10, dates shifted, private tags removed").
5. UIDs: generate new StudyInstanceUID, SeriesInstanceUID, SOPInstanceUID and FrameOfReferenceUID under our own UID root with a deterministic mapping (hash of the original UID), so references inside a study (PET to CT frame of reference, derived series) stay consistent. Store old to new mapping in the manifest. Reason: the originals are public and searchable, and a PACS fed later with the real TCIA series would collide.
6. Private tags: remove all (pydicom remove_private_tags). Every chosen series has them: group 0013 is the TCIA CTP record (project name, trial site), groups 0009, 0019, 0021, 0029, 0043, 2001 are vendor data. Also drop curves and overlays (groups 50xx and 60xx) if present.
7. Burned in pixel text: the header flag is NO or absent for all 71 series, so no series is flagged by the tag. Still render the first, middle and last image of every series to PNG (window per modality) and look at them, because derived series (CR-04 is DERIVED SECONDARY, HN-01 axial is DERIVED SECONDARY, the FDG-PET-CT-Lesions series are DERIVED SECONDARY, CUP-04 chest is a reformat) are the usual place for burned-in text. Mammograms carry laterality and view markers burned in; those are not identifying and stay. If any text with a name, date or ID is seen, drop the series and take the reserve.
8. FACE CHECK (our own privacy step, not a licence condition): for every series that may reach above the skull base (HN-01 to HN-04, LU-01 to LU-05 PET and PET-CT series, CX-04 PET-CT), look at the top slices after extraction. If the orbits, nose or mouth are in the field, either crop the slices above the hard palate (record the removed instance numbers in the manifest, renumber nothing) or run a defacing tool, before loading the PACS. The FDG-PET-CT-Lesions series are already defaced by the submitter.
9. Verify after writing: re-read every output file with pydicom, assert that no element still contains the source PatientID string, the collection name, or a date before 2020; assert pixel data hash is unchanged for uncropped series; count images per series against the table.

## 5. Attribution text for the PACS about page, and manifest fields

Suggested about page text (plain, the doctors will read it):

> About the images. The radiology images in this demonstration PACS are de-identified public research images from The Cancer Imaging Archive (TCIA), a service of the US National Cancer Institute, used under the Creative Commons Attribution licences stated below. They have been relabelled with invented patient names, identification numbers, dates and institution names for demonstration only. No image belongs to the patient named on screen. Changes made by Vaidyx: DICOM header rewritten (patient identity, dates, institution, physicians, study identifiers), private tags removed, new DICOM UIDs assigned, and in a few series the top slices removed; pixel values are otherwise unchanged. The Chinese Mammography Database (CMMD), Lung-PET-CT-Dx and StageII-Colorectal-CT were collected in China; the TCGA, CPTAC, CMB, NSCLC Radiogenomics, LIDC-IDRI, Colorectal-Liver-Metastases, Mediastinal-Lymph-Node-SEG and CC-Tumor-Heterogeneity collections in the USA and other TCGA sites; FDG-PET-CT-Lesions in Germany; TCGA-CESC in Brazil. The source collections, their licences and the required citations are listed below. The licensors do not endorse Vaidyx or this demonstration. Do not attempt to re-identify any person from these images.
>
> Source collections (name, licence, DOI): CMMD, CC BY 4.0, https://doi.org/10.7937/tcia.eqde-4b16; TCGA-BRCA, CC BY 3.0, https://doi.org/10.7937/K9/TCIA.2016.AB2NAZRP; CMB-BRCA, CC BY 4.0, https://doi.org/10.7937/dx22-8j71; Lung-PET-CT-Dx, CC BY 4.0, https://doi.org/10.7937/TCIA.2020.NNC2-0461; NSCLC Radiogenomics, CC BY 3.0, https://doi.org/10.7937/K9/TCIA.2017.7hs46erv; CPTAC-LUAD, CC BY 4.0, https://doi.org/10.7937/K9/TCIA.2018.PAT12TBS; TCGA-LUAD, CC BY 3.0, https://doi.org/10.7937/K9/TCIA.2016.JGNIHEP5; LIDC-IDRI, CC BY 3.0, https://doi.org/10.7937/K9/TCIA.2015.LO9QL9SX; TCGA-CESC, CC BY 3.0, https://doi.org/10.7937/K9/TCIA.2016.SQ4M8YP4; CC-Tumor-Heterogeneity, CC BY 4.0, https://doi.org/10.7937/ERZ5-QZ59; TCGA-READ, CC BY 3.0, https://doi.org/10.7937/K9/TCIA.2016.F7PPNPNU; TCGA-COAD, CC BY 3.0, https://doi.org/10.7937/K9/TCIA.2016.HJJHBOXZ; Colorectal-Liver-Metastases, CC BY 4.0, https://doi.org/10.7937/QXK2-QG03; StageII-Colorectal-CT, CC BY 4.0, https://doi.org/10.7937/p5k5-tg43; CMB-CRC, CC BY 4.0, https://doi.org/10.7937/DJG7-GZ87; CMB-LCA, CC BY 4.0, https://doi.org/10.7937/3CX3-S132; Mediastinal-Lymph-Node-SEG, CC BY 4.0, https://doi.org/10.7937/QVAZ-JA09; FDG-PET-CT-Lesions, CC BY 4.0, https://doi.org/10.7937/gkr0-xv29; CPTAC-PDA, CC BY 4.0, https://doi.org/10.7937/K9/TCIA.2018.SC20FO18.
>
> Licences: Creative Commons Attribution 3.0 Unported, https://creativecommons.org/licenses/by/3.0/ ; Creative Commons Attribution 4.0 International, https://creativecommons.org/licenses/by/4.0/ .
>
> Citations: the full data citation of each collection as listed in section 1 of this plan, plus Clark, K., et al. (2013). The Cancer Imaging Archive (TCIA): Maintaining and Operating a Public Information Repository. Journal of Digital Imaging, 26(6), 1045 to 1057. https://doi.org/10.1007/s10278-013-9622-7 . For the TCGA collections: "The results shown here are in whole or part based upon data generated by the TCGA Research Network: https://www.cancer.gov/tcga."

Why this satisfies CC BY: both 3.0 and 4.0 allow commercial use and modification, and require attribution (creator or attribution party, title, source link, licence name and link), a note that changes were made, and no suggestion of endorsement. TCIA adds: full data citation with DOI, the TCIA paper, and the policy not to re-identify. The text above covers each point. The TCIA Data Usage Policies page states "Most data are freely available to browse, download, and use for commercial, scientific and educational purposes" (fetched 2026-10-18).

Manifest (one JSON or CSV row per imported series; also keep a per patient table). Fields:

- demo_slot (for example BR-03), demo_group (breast, lung, cervix, colorectal, head and neck stand-in, cup), demo_patient_id, demo_patient_name, demo_dob, demo_sex, demo_hospital
- source_collection, source_patient_id, source_study_uid, source_series_uid, source_study_date, source_series_description, source_body_part, source_modality, source_manufacturer, source_model
- new_study_uid, new_series_uid, new_study_date, date_shift_days, new_accession
- image_count_expected, image_count_imported, slices_removed (list of instance numbers, empty if none), pixel_hash_unchanged (true or false)
- licence_name (exact API LicenseName), licence_url, collection_doi, collection_citation, collection_page_url, tcia_citation
- download_url, download_date, zip_filename, zip_bytes, zip_md5
- header_check: burned_in_annotation_tag (NO or absent), visual_text_check (pass or fail, who, date), face_check (not applicable, pass, cropped, defaced)
- origin_country (China, USA, Germany, Brazil, multi-site), stand_in (true for the head and neck group), notes

## 6. Open items and things marked not verified

- Head and neck: no CC BY head and neck cancer images exist on TCIA now. Options for the owner to decide: (a) accept the stand-ins above and say so on screen; (b) ask a partner hospital for one consented, locally de-identified neck CT; (c) apply for NIH controlled access, which fails the hard rule (dbGaP account, senior investigator, data use agreement) and is not recommended.
- Per patient diagnoses for Mediastinal-Lymph-Node-SEG cases and for LIDC-IDRI-0001 are not in the DICOM and were not looked up: not verified.
- The Lung-PET-CT-Dx prefix meaning (A = adenocarcinoma) is from the collection description as I remember it: not verified in this session.
- The middle author names of the Clark et al. 2013 citation: not verified from the page in this session (see section 1).
- The co-author list of CC-Tumor-Heterogeneity and the full 57 name author list of LIDC-IDRI: to be copied from the collection pages.
- Face coverage of the FACE CHECK series can only be judged after download.
- Working files from this session (API responses, not image data): /tmp/claude-1003/-home-bharath-tangella-vaidyx/1b6283bf-9372-4a28-8719-11ae9768fdee/scratchpad/pacs/ (series/*.json per collection, picks.json, picks_tags.json, picks_studies.json, download_tcia.sh, curl_commands.txt). One connectivity probe of getImage streamed a 28 MB zip to /dev/null (the server ignored the Range header); nothing was stored.
