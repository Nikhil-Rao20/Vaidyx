import{t as e}from"./jsx-runtime-BIUEfZIL.js";import{g as t}from"./endpoints-CEZYkeAC.js";import{t as n}from"./Cta-8V3JcTCs.js";import{g as r,i,r as a,t as o}from"./SiteFrame-CLAQBLVb.js";import{t as s}from"./download-BB2n9m8b.js";import{t as c}from"./external-link-Cijcg1MN.js";import{t as l}from"./PageHead-D17S01st.js";var u={models:[{key:`gemma-4-31b-it`,name:`Gemma-4-31B-it`,params:`31B`,developer:`Google DeepMind`,country:`USA`,type:`Non-medical`,images:!0,previous:!1},{key:`huatuogpt-3-27b`,name:`HuatuoGPT-3-27B`,params:`27B`,developer:`FreedomIntelligence, CUHK-Shenzhen`,country:`China`,type:`Medical`,images:!0,previous:!1},{key:`qwen3.5-4b`,name:`Qwen3.5-4B`,params:`4B`,developer:`Alibaba Qwen team`,country:`China`,type:`Non-medical`,images:!0,previous:!1},{key:`medgemma-27b-text-it`,name:`MedGemma-27B-text-it`,params:`27B`,developer:`Google`,country:`USA`,type:`Medical`,images:!1,previous:!1},{key:`medgemma-27b-it`,name:`MedGemma-27B-it`,params:`27B`,developer:`Google`,country:`USA`,type:`Medical`,images:!0,previous:!0},{key:`baichuan-m2-32b`,name:`Baichuan-M2-32B`,params:`32B`,developer:`Baichuan AI`,country:`China`,type:`Medical`,images:!1,previous:!1},{key:`lingshu-32b`,name:`Lingshu-32B`,params:`32B`,developer:`Alibaba DAMO Academy`,country:`China`,type:`Medical`,images:!0,previous:!1},{key:`medgemma-4b-it`,name:`MedGemma-4B-it`,params:`4B`,developer:`Google`,country:`USA`,type:`Medical`,images:!0,previous:!0},{key:`med42-8b`,name:`Med42-8B (v2)`,params:`8B`,developer:`M42 Health`,country:`UAE`,type:`Medical`,images:!1,previous:!0},{key:`jsl-med-8b`,name:`JSL-MedLlama-3-8B-v2.0`,params:`8B`,developer:`John Snow Labs`,country:`USA`,type:`Medical`,images:!1,previous:!0},{key:`medgemma-1.5-4b-it`,name:`MedGemma-1.5-4B-it`,params:`4B`,developer:`Google`,country:`USA`,type:`Medical`,images:!0,previous:!0},{key:`openbiollm-8b`,name:`OpenBioLLM-8B`,params:`8B`,developer:`Saama AI Labs`,country:`USA`,type:`Medical`,images:!1,previous:!0},{key:`medllama2-7b`,name:`MedLlama2-7B`,params:`7B`,developer:`Community fine-tune of Llama 2`,country:`USA`,type:`Medical`,images:!1,previous:!0}],dataCards:[{key:`medqa`,name:`MedQA`,kind:`text`,tests:`US medical licensing exam (USMLE) style clinical vignettes: diagnosis, next step, mechanism`,n:`1,273 (test)`,fmt:`4 options`,chance:`25 %`,scoring:`Letter accuracy`},{key:`medmcqa`,name:`MedMCQA`,kind:`text`,tests:`Indian postgraduate medical entrance exams (AIIMS, NEET-PG) across 21 subjects; the most India-relevant text test`,n:`4,183 (validation; test answers are hidden)`,fmt:`4 options`,chance:`25 %`,scoring:`Letter accuracy`},{key:`pubmedqa`,name:`PubMedQA`,kind:`text`,tests:`Reading a research abstract and answering a yes / no / maybe question about it (evidence reading, not recall)`,n:`1,000 (expert-labelled)`,fmt:`yes / no / maybe`,chance:`33 %`,scoring:`Label accuracy`},{key:`mmlu_med`,name:`MMLU-Med`,kind:`text`,tests:`Six medical subjects of MMLU: anatomy, clinical knowledge, college biology, college medicine, medical genetics, professional medicine`,n:`1,089 (test)`,fmt:`4 options`,chance:`25 %`,scoring:`Letter accuracy`},{key:`medxpertqa`,name:`MedXpertQA`,kind:`text`,tests:`Expert-level, deliberately hard questions from 17 specialty board exams, filtered so that strong models fail them; text subset`,n:`2,450 (test)`,fmt:`10 options`,chance:`10 %`,scoring:`Letter accuracy`},{key:`vqa_rad`,name:`VQA-RAD`,kind:`image`,tests:`Radiology images (CT, MRI, X-ray) with clinician-written questions`,n:`451 (test)`,fmt:`yes/no and short answer`,chance:`varies`,scoring:`Yes/no exact; short answers exact match after normalising`},{key:`slake`,name:`SLAKE`,kind:`image`,tests:`Radiology images with organ, position and abnormality questions (English subset)`,n:`1,061 (test)`,fmt:`yes/no and short answer`,chance:`varies`,scoring:`As VQA-RAD`},{key:`pathvqa`,name:`PathVQA`,kind:`image`,tests:`Pathology images and textbook figures; open answers are long medical phrases, so exact match is strict`,n:`6,719 (test)`,fmt:`yes/no and short answer`,chance:`varies`,scoring:`As VQA-RAD`},{key:`pmc_vqa`,name:`PMC-VQA`,kind:`image`,tests:`Figures from PubMed Central papers (all modalities), cleaned test set`,n:`2,000 (test_clean)`,fmt:`4 options`,chance:`25 %`,scoring:`Letter accuracy`},{key:`medxpertqa_mm`,name:`MedXpertQA-MM`,kind:`image`,tests:`Expert board-exam questions that need one or more clinical images plus a vignette`,n:`2,000 (test)`,fmt:`5 options`,chance:`20 %`,scoring:`Letter accuracy`},{key:`omnimedvqa`,name:`OmniMedVQA`,kind:`image`,tests:`Open-access part of OmniMedVQA: 42 public datasets, 8 modalities (MRI, CT, ultrasound, X-ray, dermoscopy, microscopy, fundus, OCT); mostly modality, anatomy and disease recognition`,n:`88,996`,fmt:`2 to 4 options`,chance:`about 27 %`,scoring:`Letter accuracy`}],thinkingOff:[`baichuan-m2-32b`,`huatuogpt-3-27b`,`qwen3.5-4b`],textCot:[{key:`gemma-4-31b-it`,acc:[93.24,78.53,80.7,94.58,55.14],overall:76.63593096548274,minParsed:100},{key:`huatuogpt-3-27b`,acc:[91.04,75.33,81.4,92.47,40.37],overall:71.23618209104552,minParsed:97.67},{key:`qwen3.5-4b`,acc:[82.17,67.97,78.7,88.43,24.29],overall:62.37435617808905,minParsed:96.94},{key:`medgemma-27b-text-it`,acc:[80.2,71.55,74.7,88.89,19.31],overall:62.050921460730365,minParsed:81.8},{key:`medgemma-27b-it`,acc:[83.11,68.52,76.9,87.6,21.18],overall:61.69140470235117,minParsed:92.41},{key:`baichuan-m2-32b`,acc:[81.3,69.42,68.7,88.89,21.39],overall:61.20915157578789,minParsed:99.92},{key:`lingshu-32b`,acc:[76.67,62.73,80.3,84.02,20.24],overall:58.16771185592797,minParsed:99.52},{key:`medgemma-4b-it`,acc:[66.06,56.11,75.8,71.26,14.45],overall:50.78610805402702,minParsed:99.02},{key:`med42-8b`,acc:[62.69,58.62,57.9,73.74,13.84],overall:49.737137568784384,minParsed:74.9},{key:`jsl-med-8b`,acc:[58.84,55.51,76.3,72.91,12.53],overall:49.374601300650326,minParsed:98.2},{key:`medgemma-1.5-4b-it`,acc:[46.9,50.47,60.9,64.65,10.2],overall:42.7327223611806,minParsed:70.62},{key:`openbiollm-8b`,acc:[49.88,47.98,52.6,67.49,11.8],overall:41.94138969484742,minParsed:91.4},{key:`medllama2-7b`,acc:[38.18,34.88,69.9,48.3,10.53],overall:34.297486743371685,minParsed:95.82}],textDirect:[{key:`huatuogpt-3-27b`,acc:[83.74,70.43,80.8,90.17,32.61],overall:66.04295547773887,overallFt:66.04295547773887,minParsed:99.92,rescored:!1,cotGain:5.193226613306649},{key:`lingshu-32b`,acc:[74.31,65.79,79.2,85.95,22.69],overall:59.84854927463732,overallFt:59.84854927463732,minParsed:100,rescored:!1,cotGain:-1.680837418709352},{key:`gemma-4-31b-it`,acc:[68.42,71.74,79.6,90.17,11.06],overall:59.23753976988494,overallFt:68.78456528264132,minParsed:21.84,rescored:!1,cotGain:17.398391195597803},{key:`baichuan-m2-32b`,acc:[74.6,67.1,71.7,86.9,17.9],overall:58.6,overallFt:null,minParsed:null,rescored:!0,cotGain:2.609151575787891},{key:`medgemma-27b-it`,acc:[66.3,60.72,77.2,80.99,12.29],overall:53.41673536768384,overallFt:55.52735567783891,minParsed:70.37,rescored:!1,cotGain:8.27466933466733},{key:`qwen3.5-4b`,acc:[67.64,57.97,76.5,78.97,16.2],overall:53.1048084042021,overallFt:53.1048084042021,minParsed:100,rescored:!1,cotGain:9.269547773886949},{key:`med42-8b`,acc:[62.06,60.1,77.2,72.91,15.14],overall:52.43548474237119,overallFt:52.45641020510254,minParsed:99.9,rescored:!1,cotGain:-2.6983471735868036},{key:`jsl-med-8b`,acc:[45.01,56.51,77.2,67.86,10.04],overall:46.96114057028514,overallFt:47.79187493746874,minParsed:74.55,rescored:!1,cotGain:2.4134607303651876},{key:`medgemma-4b-it`,acc:[55.22,52.04,74.9,64.92,13.18],overall:46.61003101550776,overallFt:46.612781390695346,minParsed:99.96,rescored:!1,cotGain:4.17607703851926},{key:`openbiollm-8b`,acc:[43.68,40.31,44.4,58.22,9.1],overall:35.44951975987994,overallFt:39.15781990995498,minParsed:59.9,rescored:!1,cotGain:6.491869934967482},{key:`medgemma-27b-text-it`,acc:[8.01,38.23,72.3,49.04,1.96],overall:30.07697648824412,overallFt:46.65180790395198,minParsed:14.2,rescored:!1,cotGain:31.973944972486244},{key:`medgemma-1.5-4b-it`,acc:[17.75,40.71,56.1,41.51,1.67],overall:29.843078539269637,overallFt:35.740304152076035,minParsed:16.29,rescored:!1,cotGain:12.889643821910962},{key:`medllama2-7b`,acc:[16.42,33.21,68,40.31,4.12],overall:28.195265632816408,overallFt:33.34701550775387,minParsed:38.57,rescored:!1,cotGain:6.102221110555277}],textFirstToken:[{key:`huatuogpt-3-27b`,acc:[83.74,70.43,80.8,90.17,32.61],overall:66.04295547773887},{key:`lingshu-32b`,acc:[74.31,65.79,79.2,85.95,22.69],overall:59.84854927463732},{key:`gemma-4-31b-it`,acc:[82.72,72.34,79.6,91.55,40.94],overall:68.78456528264132},{key:`medgemma-27b-it`,acc:[70.15,61.8,77.4,81.63,16.69],overall:55.52735567783891},{key:`qwen3.5-4b`,acc:[67.64,57.97,76.5,78.97,16.2],overall:53.1048084042021},{key:`med42-8b`,acc:[62.06,60.15,77.2,72.91,15.14],overall:52.45641020510254},{key:`jsl-med-8b`,acc:[53.26,54.55,72,71.44,13.02],overall:47.79187493746874},{key:`medgemma-4b-it`,acc:[55.22,52.07,74.9,64.92,13.14],overall:46.612781390695346},{key:`openbiollm-8b`,acc:[43.83,44.63,54.2,63.27,10.53],overall:39.15781990995498},{key:`medgemma-27b-text-it`,acc:[37.86,57.11,72.3,64.19,15.1],overall:46.65180790395198},{key:`medgemma-1.5-4b-it`,acc:[35.19,42.82,57.8,46.19,10.29],overall:35.740304152076035},{key:`medllama2-7b`,acc:[37.08,36.03,67.7,40.31,9.71],overall:33.34701550775387}],publishedText:[{key:`medgemma-27b-text-it`,src:`Google card`,ours:[80.2,71.55,74.7,88.89,19.31],published:[87.7,74.2,76.8,87,25.7]},{key:`medgemma-27b-it`,src:`Google card`,ours:[83.11,68.52,76.9,87.6,21.18],published:[85.3,70.2,77.2,86.2,23.7]},{key:`lingshu-32b`,src:`Lingshu report`,ours:[76.67,62.73,80.3,84.02,20.24],published:[74.7,66.1,77.8,84.7,22.7]},{key:`medgemma-4b-it`,src:`Google card`,ours:[66.06,56.11,75.8,71.26,14.45],published:[64.4,55.7,73.4,70,14.2]},{key:`med42-8b`,src:`M42 card$^{a}$`,ours:[62.69,58.62,57.9,73.74,13.84],published:[62.8,61.3,null,75.8,null]},{key:`jsl-med-8b`,src:`JSL card$^{b}$`,ours:[58.84,55.51,76.3,72.91,12.53],published:[61.4,61.2,74.2,77.6,null]},{key:`medgemma-1.5-4b-it`,src:`Google card`,ours:[46.9,50.47,60.9,64.65,10.2],published:[69.1,59.8,68.2,69.6,16.4]},{key:`openbiollm-8b`,src:`Saama card$^{b}$`,ours:[49.88,47.98,52.6,67.49,11.8],published:[59,56.9,74.1,77.1,null]}],q4:[{key:`medgemma-27b-it`,q4:[69.8,62.1,76.1,79.2,16.6],direct:[66.3,60.72,77.2,80.99,12.29],cot:[83.11,68.52,76.9,87.6,21.18]},{key:`medgemma-4b-it`,q4:[51.8,47.5,71.4,60.6,12.7],direct:[55.22,52.04,74.9,64.92,13.18],cot:[66.06,56.11,75.8,71.26,14.45]},{key:`med42-8b`,q4:[60.4,57.9,75.6,71.7,12.4],direct:[62.06,60.1,77.2,72.91,15.14],cot:[62.69,58.62,57.9,73.74,13.84]},{key:`jsl-med-8b`,q4:[27.6,31,36,21.6,9.3],direct:[45.01,56.51,77.2,67.86,10.04],cot:[58.84,55.51,76.3,72.91,12.53]},{key:`medgemma-1.5-4b-it`,q4:[29.8,33.4,58,23.5,9.1],direct:[17.75,40.71,56.1,41.51,1.67],cot:[46.9,50.47,60.9,64.65,10.2]},{key:`openbiollm-8b`,q4:[24.5,25.4,44.7,23,9.1],direct:[43.68,40.31,44.4,58.22,9.1],cot:[49.88,47.98,52.6,67.49,11.8]},{key:`medllama2-7b`,q4:[27,27.4,59.8,25.6,9.2],direct:[16.42,33.21,68,40.31,4.12],cot:[38.18,34.88,69.9,48.3,10.53]}],throughput:[{key:`gemma-4-31b-it`,protocol:`direct`,load:181.6,total:676.6,genTokens:8.671375687843922},{key:`gemma-4-31b-it`,protocol:`cot`,load:115.5,total:4748.7,genTokens:422.63955977988996},{key:`huatuogpt-3-27b`,protocol:`direct`,load:128.3,total:528.5,genTokens:2},{key:`huatuogpt-3-27b`,protocol:`cot`,load:82.6,total:5872.9,genTokens:872.0250825412705},{key:`qwen3.5-4b`,protocol:`direct`,load:78.2,total:148.7,genTokens:2},{key:`qwen3.5-4b`,protocol:`cot`,load:57.1,total:1262.8,genTokens:805.4461830915458},{key:`medgemma-27b-text-it`,protocol:`direct`,load:118.3,total:384.8,genTokens:20.187883941970988},{key:`medgemma-27b-text-it`,protocol:`cot`,load:68.5,total:9225.3,genTokens:1342.2257428714358},{key:`medgemma-27b-it`,protocol:`direct`,load:116.4,total:351,genTokens:5.3657528764382185},{key:`medgemma-27b-it`,protocol:`cot`,load:58.7,total:2415.2,genTokens:1146.651115557779},{key:`baichuan-m2-32b`,protocol:`direct`,load:86,total:542.1,genTokens:5.900910455227614},{key:`baichuan-m2-32b`,protocol:`cot`,load:54.7,total:3166.5,genTokens:482.07060530265124},{key:`lingshu-32b`,protocol:`direct`,load:91.3,total:548.2,genTokens:3},{key:`lingshu-32b`,protocol:`cot`,load:60.2,total:1833.4,genTokens:271.0742971485743},{key:`medgemma-4b-it`,protocol:`direct`,load:84.2,total:113.9,genTokens:3},{key:`medgemma-4b-it`,protocol:`cot`,load:32.9,total:575.7,genTokens:259.8870835417709},{key:`med42-8b`,protocol:`direct`,load:39.4,total:98.5,genTokens:6.446363181590796},{key:`med42-8b`,protocol:`cot`,load:38.3,total:385.7,genTokens:236.04956478239123},{key:`jsl-med-8b`,protocol:`direct`,load:55,total:174.6,genTokens:31.958149074537264},{key:`jsl-med-8b`,protocol:`cot`,load:38.5,total:595.8,genTokens:205.8207003501751},{key:`medgemma-1.5-4b-it`,protocol:`direct`,load:74.2,total:147.7,genTokens:13.302011005502752},{key:`medgemma-1.5-4b-it`,protocol:`cot`,load:32.8,total:1881.6,genTokens:1278.296308154077},{key:`openbiollm-8b`,protocol:`direct`,load:57.1,total:165.2,genTokens:27.282971485742877},{key:`openbiollm-8b`,protocol:`cot`,load:40.5,total:395.3,genTokens:31.081700850425214},{key:`medllama2-7b`,protocol:`direct`,load:43.1,total:161.9,genTokens:26.58933466733367},{key:`medllama2-7b`,protocol:`cot`,load:34.1,total:604.6,genTokens:148.81884942471234}],image:[{key:`huatuogpt-3-27b`,overall:{vqa_rad:54.55,slake:60.32,pathvqa:38.89,pmc_vqa:59.3,medxpertqa_mm:33.25,omnimedvqa:82.88},cot:{pmc_vqa:62.7,medxpertqa_mm:49.7},omniFt:82.89,omniParsed:98.94,omniErrors:922,split:{vqa_rad:[75.7,28],slake:[82.82,45.89],pathvqa:[71.51,6.23]},byType:[96.2,84,80.3,70.4,82.7]},{key:`lingshu-32b`,overall:{vqa_rad:67.41,slake:84.92,pathvqa:59.93,pmc_vqa:64.9,medxpertqa_mm:31.05,omnimedvqa:82.4},cot:{pmc_vqa:60.15,medxpertqa_mm:31.5},omniFt:82.4,omniParsed:98.83,omniErrors:1043,split:{vqa_rad:[88.05,41.5],slake:[91.27,81.24],pathvqa:[89.86,29.97]},byType:[96.7,82.1,79.5,77.6,85.8]},{key:`gemma-4-31b-it`,overall:{vqa_rad:51.44,slake:51.46,pathvqa:36.79,pmc_vqa:45.1,medxpertqa_mm:2.4,omnimedvqa:77},cot:{pmc_vqa:66.15,medxpertqa_mm:55.45},omniFt:81.5,omniParsed:92.18,omniErrors:0,split:{vqa_rad:[75.3,21.5],slake:[87.04,29.77],pathvqa:[70.35,3.19]},byType:[99.3,79.5,78.7,65.5,86.5]},{key:`qwen3.5-4b`,overall:{vqa_rad:55.65,slake:59.57,pathvqa:39.81,pmc_vqa:16.25,medxpertqa_mm:.65,omnimedvqa:27.55},cot:{pmc_vqa:60.05,medxpertqa_mm:35.5},omniFt:74.21,omniParsed:35.37,omniErrors:922,split:{vqa_rad:[77.69,28],slake:[85.63,44.03],pathvqa:[75.28,4.29]},byType:[96.7,76.3,69.8,52.8,72.4]},{key:`medgemma-4b-it`,overall:{vqa_rad:56.76,slake:52.78,pathvqa:33.07,pmc_vqa:46.2,medxpertqa_mm:24.05,omnimedvqa:70.28},cot:{pmc_vqa:46.5,medxpertqa_mm:25.4},omniFt:70.44,omniParsed:99.49,omniErrors:0,split:{vqa_rad:[80.88,26.5],slake:[86.76,32.09],pathvqa:[64.43,1.67]},byType:[96.8,57.8,68.4,70.4,74.8]},{key:`medgemma-27b-it`,overall:{vqa_rad:50.55,slake:49.95,pathvqa:32.13,pmc_vqa:38.2,medxpertqa_mm:4.35,omnimedvqa:61.93},cot:{pmc_vqa:47.15,medxpertqa_mm:33.25},omniFt:68.57,omniParsed:87.26,omniErrors:0,split:{vqa_rad:[76.89,17.5],slake:[82.25,29.77],pathvqa:[63.12,1.1]},byType:[88,47.9,69.7,77.7,77.4]},{key:`medgemma-1.5-4b-it`,overall:{vqa_rad:41.24,slake:35.72,pathvqa:27.73,pmc_vqa:17.6,medxpertqa_mm:.25,omnimedvqa:19.07},cot:{pmc_vqa:45,medxpertqa_mm:9.6},omniFt:68.15,omniParsed:22.3,omniErrors:0,split:{vqa_rad:[62.15,15],slake:[77.75,12.87],pathvqa:[54.85,.57]},byType:[81.9,61.4,67.6,67.6,63.7]}],omniTypes:[`Modality recognition`,`Anatomy identification`,`Disease diagnosis`,`Lesion grading`,`Other biological attributes`],publishedImage:[{key:`lingshu-32b`,benchmark:`OmniMedVQA`,ours:82.4,protocol:`first-token`,published:83.4,src:`Lingshu paper`,like:`Yes`},{key:`lingshu-32b`,benchmark:`PMC-VQA`,ours:64.9,protocol:`direct`,published:57.9,src:`Lingshu paper`,like:`Yes`},{key:`lingshu-32b`,benchmark:`MedXpertQA-MM`,ours:31.5,protocol:`CoT`,published:30.9,src:`Lingshu paper`,like:`Yes`},{key:`lingshu-32b`,benchmark:`SLAKE`,ours:84.9,protocol:`exact match`,published:89.2,src:`Lingshu paper`,like:`No: GPT-4.1 judges open answers`},{key:`lingshu-32b`,benchmark:`VQA-RAD`,ours:67.4,protocol:`exact match`,published:76.5,src:`Lingshu paper`,like:`No: GPT-4.1 judges open answers`},{key:`lingshu-32b`,benchmark:`PathVQA`,ours:59.9,protocol:`exact match`,published:65.9,src:`Lingshu paper`,like:`No: GPT-4.1 judges open answers`},{key:`medgemma-4b-it`,benchmark:`OmniMedVQA`,ours:70.4,protocol:`first-token`,published:69.8,src:`Lingshu paper`,like:`Yes`},{key:`medgemma-4b-it`,benchmark:`PMC-VQA`,ours:46.2,protocol:`direct`,published:49.9,src:`Lingshu paper`,like:`Yes`},{key:`medgemma-4b-it`,benchmark:`SLAKE closed (yes/no)`,ours:86.8,protocol:`yes/no`,published:87.6,src:`Google card`,like:`Yes`},{key:`medgemma-4b-it`,benchmark:`VQA-RAD closed (yes/no)`,ours:80.9,protocol:`yes/no`,published:69.1,src:`Google card`,like:`Yes`},{key:`medgemma-4b-it`,benchmark:`MedXpertQA-MM`,ours:25.4,protocol:`CoT`,published:18.8,src:`Google card`,like:`Yes`},{key:`medgemma-27b-it`,benchmark:`SLAKE closed (yes/no)`,ours:82.2,protocol:`yes/no`,published:85.9,src:`Google 1.5 card`,like:`Yes`},{key:`medgemma-27b-it`,benchmark:`VQA-RAD closed (yes/no)`,ours:76.9,protocol:`yes/no`,published:67.1,src:`Google 1.5 card`,like:`Yes`},{key:`medgemma-27b-it`,benchmark:`MedXpertQA-MM`,ours:33.2,protocol:`CoT`,published:26.8,src:`Google card`,like:`Roughly: card mixes text and image items`},{key:`medgemma-1.5-4b-it`,benchmark:`SLAKE closed (yes/no)`,ours:77.8,protocol:`yes/no`,published:82.8,src:`Google 1.5 card`,like:`Yes`},{key:`medgemma-1.5-4b-it`,benchmark:`VQA-RAD closed (yes/no)`,ours:62.1,protocol:`yes/no`,published:70.2,src:`Google 1.5 card`,like:`Yes`},{key:`medgemma-1.5-4b-it`,benchmark:`MedXpertQA-MM`,ours:9.6,protocol:`CoT`,published:20.9,src:`Google 1.5 card`,like:`Yes`},{key:`gemma-4-31b-it`,benchmark:`MedXpertQA-MM`,ours:55.5,protocol:`CoT`,published:61.3,src:`Gemma 4 report`,like:`Roughly: report uses thinking mode`},{key:`qwen3.5-4b`,benchmark:`PMC-VQA`,ours:60,protocol:`CoT`,published:55.5,src:`Qwen card`,like:`Roughly: card uses thinking mode`},{key:`qwen3.5-4b`,benchmark:`MedXpertQA-MM`,ours:35.5,protocol:`CoT`,published:42.9,src:`Qwen card`,like:`Roughly: card uses thinking mode`},{key:`qwen3.5-4b`,benchmark:`SLAKE`,ours:59.6,protocol:`exact match`,published:76.1,src:`Qwen card`,like:`No: scoring not stated`}],bakeoff:[{key:`qwen3.5-4b`,readerRecall:`1.000`,invented:`0`,readerS:`1.6`,types:`31/31`,fields:`49/49`,fabricated:`0`,extractorS:`4.8`},{key:`gemma-4-31b-it`,readerRecall:`1.000`,invented:`0`,readerS:`11.1`,types:`30/31`,fields:`49/49`,fabricated:`0`,extractorS:`28.1`},{key:`medgemma-27b-it`,readerRecall:`0.976`,invented:`1`,readerS:`7.9`,types:`31/31`,fields:`49/49`,fabricated:`0`,extractorS:`23.0`},{key:`lingshu-32b`,readerRecall:`0.994`,invented:`0`,readerS:`11.3`,types:`31/31`,fields:`48/49`,fabricated:`0`,extractorS:`22.5`},{key:`huatuogpt-3-27b`,readerRecall:`1.000`,invented:`0`,readerS:`8.4`,types:`30/31`,fields:`49/49`,fabricated:`0`,extractorS:`27.2`},{key:`medgemma-27b-text-it`,readerRecall:`text only`,invented:`--`,readerS:`--`,types:`30/31`,fields:`49/49`,fabricated:`0`,extractorS:`23.3`}],answerability:[{key:`gemma-4-31b-it`,pass_:`33/33`,fabrications:`0`,latency:`3.0`},{key:`huatuogpt-3-27b`,pass_:`32/33`,fabrications:`0`,latency:`8.0`},{key:`medgemma-27b-it`,pass_:`31/33`,fabrications:`0`,latency:`8.4`}],tcga:{reports:30,claims:166,ungrounded:0,agreement:[[`ER`,`7/8`],[`PR`,`7/8`],[`Histology`,`27/29`],[`pT (as recorded)`,`24/26`]]},status:{reports:9523,rows:[[`FINAL DIAGNOSIS`,`26 %`],[`ADDENDUM`,`15 %`],[`verified / reviewed by`,`14 %`],[`signed`,`5 %`],[`end of report`,`3 %`],[`no explicit status or signature`,`61 %`]]},ocr:[{engine:`Tesseract 5.5.3 (psm 4)`,recall:`98.6`,precision:`98.4`,sPage:`0.395`,threads:`1`},{engine:`docTR 1.1.0 (rows)`,recall:`97.7`,precision:`95.8`,sPage:`1.276`,threads:`8`},{engine:`docTR 1.1.0 (native block lines)`,recall:`17.8`,precision:`17.6`,sPage:`1.276`,threads:`8`}],ocrCheck:[{check:`3.3 rule as is`,falseAlarms:`54`,subs:`99.6`,ins:`99.8`,dels:`99.7`},{check:`Substitution, one read`,falseAlarms:`2`,subs:`99.4`,ins:`2.0`,dels:`2.7`},{check:`Substitution, confirming re-read`,falseAlarms:`0`,subs:`99.4`,ins:`0.2`,dels:`0.3`},{check:`Shipped: substitution, insertion, deletion, confirming re-read`,falseAlarms:`0`,subs:`99.4`,ins:`90.3`,dels:`87.9`}],experiments:{ciText:[{key:`gemma-4-31b-it`,cot:[76.64,75.87,77.41],direct:[59.24,58.45,60.04],medxpertqa:[55.14,53.22,57.02]},{key:`huatuogpt-3-27b`,cot:[71.24,70.43,72.06],direct:[66.04,65.19,66.88],medxpertqa:[40.37,38.41,42.29]},{key:`qwen3.5-4b`,cot:[62.37,61.55,63.22],direct:[53.11,52.24,54.01],medxpertqa:[24.29,22.57,25.96]},{key:`medgemma-27b-text-it`,cot:[62.05,61.22,62.87],direct:[30.08,29.24,30.87],medxpertqa:[19.31,17.8,20.86]},{key:`medgemma-27b-it`,cot:[61.69,60.87,62.53],direct:[53.42,52.57,54.26],medxpertqa:[21.18,19.59,22.82]},{key:`baichuan-m2-32b`,cot:[61.21,60.35,62.02],direct:[58.6,57.75,59.43],medxpertqa:[21.39,19.8,23.06]},{key:`lingshu-32b`,cot:[58.17,57.32,59.05],direct:[59.85,58.99,60.73],medxpertqa:[20.24,18.57,21.84]},{key:`medgemma-4b-it`,cot:[50.79,49.92,51.64],direct:[46.61,45.71,47.48],medxpertqa:[14.45,13.06,15.88]},{key:`med42-8b`,cot:[49.73,48.87,50.66],direct:[52.44,51.55,53.33],medxpertqa:[13.84,12.49,15.22]},{key:`jsl-med-8b`,cot:[49.37,48.49,50.24],direct:[46.96,46.08,47.83],medxpertqa:[12.53,11.22,13.84]},{key:`medgemma-1.5-4b-it`,cot:[42.73,41.84,43.62],direct:[29.84,29.04,30.64],medxpertqa:[10.2,9.02,11.35]},{key:`openbiollm-8b`,cot:[41.94,41.05,42.81],direct:[35.45,34.56,36.32],medxpertqa:[11.8,10.53,13.1]},{key:`medllama2-7b`,cot:[34.3,33.4,35.16],direct:[28.19,27.39,28.98],medxpertqa:[10.53,9.31,11.76]}],paired:[{comparison:`Gemma-4-31B vs HuatuoGPT-3, CoT overall`,diff:5.4,lo:4.61,hi:6.15,a_only:1068,b_only:528,p_mcnemar:285e-44},{comparison:`HuatuoGPT-3 vs Qwen3.5-4B, CoT overall`,diff:8.86,lo:7.97,hi:9.74,a_only:1471,b_only:585,p_mcnemar:133e-89},{comparison:`Qwen3.5-4B vs MedGemma-27B-it, CoT overall ('matches')`,diff:.68,lo:-.17,hi:1.54,a_only:1012,b_only:944,p_mcnemar:.13},{comparison:`Qwen3.5-4B vs MedGemma-27B-it, CoT MedQA`,diff:-.94,lo:-3.22,hi:1.34,a_only:107,b_only:119,p_mcnemar:.464},{comparison:`Qwen3.5-4B vs MedGemma-27B-text-it, CoT overall`,diff:.32,lo:-.57,hi:1.19,a_only:1033,b_only:1001,p_mcnemar:.492},{comparison:`MedGemma-27B-text-it vs MedGemma-27B-it, CoT overall`,diff:.36,lo:-.41,hi:1.14,a_only:817,b_only:781,p_mcnemar:.381},{comparison:`MedGemma-27B-it vs Baichuan-M2, CoT overall`,diff:.48,lo:-.39,hi:1.36,a_only:1017,b_only:969,p_mcnemar:.292},{comparison:`Baichuan-M2 vs Lingshu-32B, CoT overall`,diff:3.04,lo:2.16,hi:3.95,a_only:1180,b_only:876,p_mcnemar:217e-13},{comparison:`Med42-8B vs JSL-MedLlama, CoT overall`,diff:.36,lo:-.59,hi:1.35,a_only:1304,b_only:1268,p_mcnemar:.49},{comparison:`MedGemma-1.5-4B vs OpenBioLLM-8B, CoT overall`,diff:.79,lo:-.38,hi:1.88,a_only:1735,b_only:1656,p_mcnemar:.18},{comparison:`Qwen3.5-4B vs MedGemma-4B-it, CoT overall`,diff:11.59,lo:10.6,hi:12.6,a_only:1961,b_only:803,p_mcnemar:121e-112},{comparison:`Gemma-4-31B vs HuatuoGPT-3, CoT MedXpertQA`,diff:14.78,lo:12.69,hi:16.86,a_only:549,b_only:187,p_mcnemar:411e-44},{comparison:`HuatuoGPT-3 vs Lingshu-32B, direct overall`,diff:6.19,lo:5.34,hi:7.05,a_only:1359,b_only:740,p_mcnemar:464e-44},{comparison:`gemma-4-31b-it: CoT vs direct overall`,diff:17.4,lo:16.63,hi:18.15,a_only:1946,b_only:207,p_mcnemar:0},{comparison:`huatuogpt-3-27b: CoT vs direct overall`,diff:5.19,lo:4.37,hi:5.98,a_only:1084,b_only:565,p_mcnemar:715e-40},{comparison:`lingshu-32b: CoT vs direct overall`,diff:-1.68,lo:-2.52,hi:-.88,a_only:786,b_only:954,p_mcnemar:616e-7},{comparison:`med42-8b: CoT vs direct overall`,diff:-2.7,lo:-3.49,hi:-1.89,a_only:779,b_only:1049,p_mcnemar:292e-12},{comparison:`HuatuoGPT-3 vs Lingshu-32B, OmniMedVQA first-token`,diff:.49,lo:.19,hi:.77,a_only:8638,b_only:8203,p_mcnemar:824e-6},{comparison:`Lingshu-32B vs Gemma-4-31B, OmniMedVQA first-token`,diff:.91,lo:.62,hi:1.21,a_only:9708,b_only:8902,p_mcnemar:3.59e-9},{comparison:`Lingshu-32B vs HuatuoGPT-3, SLAKE`,diff:24.6,lo:21.58,hi:27.62,a_only:298,b_only:37,p_mcnemar:802e-54},{comparison:`Lingshu-32B vs MedGemma-4B, VQA-RAD`,diff:10.64,lo:5.99,hi:15.08,a_only:82,b_only:34,p_mcnemar:969e-8},{comparison:`Gemma-4-31B vs HuatuoGPT-3, MedXpertQA-MM CoT`,diff:5.75,lo:3.5,hi:8.1,a_only:348,b_only:233,p_mcnemar:209e-8},{comparison:`Gemma-4-31B vs Lingshu-32B, PMC-VQA CoT`,diff:6,lo:3.75,hi:8.2,a_only:332,b_only:212,p_mcnemar:302e-9}],oncology:{sizes:{medqa:159,medmcqa:189,medxpertqa:326},n:674,rows:[{key:`gemma-4-31b-it`,oncology:[74.04,70.92,77],rest:[73.62,72.64,74.6],direct:[45.1,42.43,47.92]},{key:`huatuogpt-3-27b`,oncology:[67.51,64.24,70.62],rest:[66.98,66,68],direct:[61.87,58.61,64.99]},{key:`qwen3.5-4b`,oncology:[54.75,51.48,58.01],rest:[56.9,55.83,57.9],direct:[43.77,40.5,46.88]},{key:`baichuan-m2-32b`,oncology:[54.75,51.63,57.87],rest:[56.61,55.61,57.61],direct:[47.48,44.51,50.74]},{key:`medgemma-27b-it`,oncology:[52.67,49.41,55.93],rest:[56.53,55.53,57.56],direct:[44.51,41.54,47.63]},{key:`lingshu-32b`,oncology:[50.45,47.18,53.71],rest:[51.94,50.88,52.93],direct:[50.15,47.03,53.26]},{key:`medgemma-27b-text-it`,oncology:[50.3,47.18,53.41],rest:[57.36,56.36,58.34],direct:[14.69,12.46,16.91]},{key:`med42-8b`,oncology:[43.03,39.76,46.15],rest:[45.62,44.58,46.67],direct:[42.73,39.47,45.99]},{key:`medgemma-4b-it`,oncology:[40.8,37.24,44.07],rest:[45.17,44.14,46.23],direct:[36.2,32.94,39.32]},{key:`jsl-med-8b`,oncology:[37.24,34.12,40.36],rest:[43.24,42.2,44.28],direct:[30.12,27,33.09]},{key:`medgemma-1.5-4b-it`,oncology:[33.23,30.27,36.5],rest:[37.8,36.78,38.87],direct:[17.36,14.99,19.73]},{key:`openbiollm-8b`,oncology:[31.45,28.04,34.57],rest:[37.6,36.56,38.62],direct:[27.6,24.48,30.71]},{key:`medllama2-7b`,oncology:[25.52,22.4,28.78],rest:[28.08,27.09,29.11],direct:[14.69,12.17,17.21]}]},tcgaScale:{reports:2102,by_project:{BRCA:1034,LUAD:488,COAD:418,READ:162},errors:3,seconds:470.8,claims:10883,ungrounded:151,ungrounded_rate_pct:1.387,ungrounded_upper95_pct:1.625,claims_per_field:{histologic_type:2091,grade:1985,lvi:1482,margins:1875,er:601,pr:596,her2:584,recorded_stage:1629,mmr:40},stated_in_extracted_stage:{pT:1280,pN:571,"stage group":77},report_says_pending:{ER:49,PR:49,"HER2 (IHC)":63},her2_fish_only:50,disagreements_with_verified_quote:{PR:{verified:52,of:53},Histology:{verified:49,of:51},"HER2 (IHC)":{verified:63,of:65},pT:{verified:35,of:36},ER:{verified:46,of:47},"Stage group":{verified:5,of:5},pN:{verified:15,of:15}},agreement:{Histology:{agree:1961,n:2012,pct:97.5,lower95_pct:96.7},pT:{agree:1244,n:1280,pct:97.2,lower95_pct:96.1},pN:{agree:556,n:571,pct:97.4,lower95_pct:95.7},ER:{agree:495,n:542,pct:91.3,lower95_pct:88.7},PR:{agree:485,n:538,pct:90.1,lower95_pct:87.3},"Stage group":{agree:70,n:75,pct:93.3,lower95_pct:85.3},"HER2 (IHC)":{agree:346,n:411,pct:84.2,lower95_pct:80.3}},model:`extractor role (Qwen3.5-4B, Chinese, non-medical), as shipped`,details_file:`/data/vaidyx/research_experiments/tcga_scale_details.jsonl`},probesScale:{ans:{n:118,pass:117,missed:1,wrong:0},absent_true_trap:{n:205,pass:205,fabrication:0},absent_documented_after_all:64,scope:{n:32,pass:32},hand_written:{n:57,pass:57},statements_removed_by_grounding:[{case:`TB-003`,probe:`absent`,field:`lesion_size`,reason:`quote_not_found`,text:`The primary tumour in the mid rectum has a craniocaudal length of 5.5 cm.`,review:`true, quote did not match`,note:`5.5 cm craniocaudal length is in the MRI report`},{case:`TB-004`,probe:`absent`,field:`comparison_prior`,reason:`number_not_in_quote`,text:`No chest imaging older than the chest X-ray from 28/08/2026 is available for comparison.`,review:`statement of absence`,note:`no older chest imaging; a date not in the quote`},{case:`TB-004`,probe:`absent`,field:`treatment_received`,reason:`quote_not_found`,text:`The patient received T ab. Amoxicillin-clavulanate 625 mg 8-hourly from 12/09/2026.`,review:`true, quote did not match`,note:`amoxicillin-clavulanate 625 mg 8-hourly is in the discharge summary`},{case:`TB-006`,probe:`ans`,field:`histologic_type`,reason:`number_not_in_quote`,text:`Histopathology from 2026-05-15 recorded the diagnosis as Adenocarcinoma, well to moderately differentiated.`,review:`wrong date caught`,note:`dates the histopathology 2026-05-15; the report is of 25/05/2026`},{case:`TB-006`,probe:`absent`,field:`lesion_size`,reason:`number_not_in_quote`,text:`A colonoscopy on 2026-05-12 recorded an ulceroproliferative growth from 8 cm to 13 cm from the anal verge.`,review:`wrong number caught`,note:`says 8 cm to 13 cm from the anal verge; the colonoscopy report says 8 cm to 12 cm`}],removed_by_review:{"statement of absence":1,"true, quote did not match":2,"wrong date caught":1,"wrong number caught":1},statements_removed_by_output_guardrail:[{case:`TB-001`,field:`histologic_type`}],generated:419}},totals:{models:13,textQuestions:9995,imageQuestions:101227,visionModels:7}},d=e(),f=e=>e==null?`–`:e.toFixed(1),p=e=>e==null?`–`:`${e>0?`+`:e<0?`−`:``}${Math.abs(e).toFixed(1)}`,m=e=>e.toLocaleString(`en-IN`);function h({v:e}){return(0,d.jsx)(`span`,{className:t(`l-chip`,e===`China`?`l-chip-warn`:`l-chip-info`),children:e})}function g({v:e}){return(0,d.jsx)(`span`,{className:t(`l-chip`,e===`Medical`?`l-chip-ok`:`l-chip-review`),children:e})}function _({n:e,caption:n,head:i,rows:o,numeric:s=[],boldMax:c=[],wrap:l=[],note:u,testId:p,size:m=`md`,maxW:h}){let g=new Map;for(let e of c){let t=-1/0;for(let n of o){let r=(Array.isArray(n)?n:n.cells)[e];typeof r==`number`&&r>t&&(t=r)}g.set(e,t)}return(0,d.jsx)(a,{y:16,amount:.1,children:(0,d.jsxs)(`figure`,{className:`l-card overflow-hidden`,"data-testid":p,style:h?{maxWidth:h}:void 0,children:[(0,d.jsxs)(`figcaption`,{className:`r-cap px-5 pb-3 pt-4 sm:px-6`,children:[(0,d.jsxs)(`b`,{children:[`Table `,e,`.`]}),` `,n]}),(0,d.jsx)(`div`,{className:`overflow-x-auto px-2 pb-2 sm:px-3`,children:(0,d.jsxs)(`table`,{className:t(`r-tbl`,m===`sm`&&`r-tbl-sm`),children:[(0,d.jsx)(`thead`,{children:(0,d.jsx)(`tr`,{children:i.map((e,n)=>(0,d.jsx)(`th`,{className:t(s.includes(n)&&`num`),children:e.split(`
`).map((e,t)=>(0,d.jsx)(`span`,{className:`block`,children:e},t))},n))})}),(0,d.jsx)(`tbody`,{children:o.map((e,n)=>{let r=Array.isArray(e)?{cells:e}:e;return(0,d.jsx)(`tr`,{className:t(r.sep&&`sep`,r.dim&&`dim`,r.strong&&`strong`),children:r.cells.map((e,n)=>{let r=s.includes(n),i=typeof e==`number`&&g.get(n)===e,a=typeof e==`number`?f(e):e===`--`?`–`:e;return(0,d.jsx)(`td`,{className:t(r&&`num`,l.includes(n)&&`wrap`,i&&`r-best`),children:a},n)})},n)})})]})}),(0,d.jsx)(`p`,{className:`r-note px-5 pb-3 sm:hidden`,children:r.swipe}),u?(0,d.jsx)(`p`,{className:`r-note border-t px-5 py-3 sm:px-6`,style:{borderColor:`var(--l-line)`},children:u}):null]})})}function v({id:e,n:t,title:n,children:r}){return(0,d.jsxs)(`section`,{id:e,className:`scroll-mt-28 pt-14 first:pt-0 sm:pt-16`,"data-testid":`research-${e}`,children:[(0,d.jsx)(a,{y:14,children:(0,d.jsxs)(`h2`,{className:`r-h2`,children:[(0,d.jsx)(`em`,{children:t}),` `,n]})}),(0,d.jsx)(`div`,{className:`mt-6 space-y-6`,children:r})]})}function y({n:e,title:t,children:n}){return(0,d.jsxs)(`div`,{className:`pt-4`,children:[(0,d.jsx)(a,{y:10,children:(0,d.jsxs)(`h3`,{className:`r-h3`,children:[(0,d.jsx)(`em`,{children:e}),` `,t]})}),(0,d.jsx)(`div`,{className:`mt-4 space-y-5`,children:n})]})}function b({children:e,className:n}){return(0,d.jsx)(a,{y:10,amount:.15,children:(0,d.jsx)(`p`,{className:t(`r-p max-w-[52rem]`,n),children:e})})}function x({items:e,as:t=`dl`}){return t===`ul`?(0,d.jsx)(`ul`,{className:`max-w-[56rem] space-y-3`,children:e.map(([e,t])=>(0,d.jsxs)(`li`,{className:`r-p flex gap-3`,children:[(0,d.jsx)(`span`,{className:`mt-[0.72em] size-1.5 shrink-0 rounded-full`,style:{background:`var(--l-accent)`},"aria-hidden":!0}),(0,d.jsxs)(`span`,{children:[(0,d.jsx)(`strong`,{children:e}),` `,t]})]},e))}):(0,d.jsx)(`dl`,{className:`r-dl grid max-w-[64rem] gap-x-8 gap-y-4 sm:grid-cols-[13rem_1fr]`,children:e.map(([e,t])=>(0,d.jsxs)(`div`,{className:`contents`,children:[(0,d.jsx)(`dt`,{className:`r-p`,children:e}),(0,d.jsx)(`dd`,{className:`r-p`,children:t})]},e))})}function S({name:e,kind:n,tests:r,n:i,fmt:a,chance:o,scoring:s,labels:c}){return(0,d.jsxs)(`div`,{className:`l-box flex h-full flex-col p-5`,children:[(0,d.jsxs)(`div`,{className:`flex items-start justify-between gap-3`,children:[(0,d.jsx)(`h4`,{className:`text-[1.05rem] font-semibold tracking-[-0.01em]`,children:e}),(0,d.jsx)(`span`,{className:t(`l-chip`,n===`image`?`l-chip-review`:`l-chip-info`),children:c.kind})]}),(0,d.jsx)(`p`,{className:`r-cap mt-2`,children:r}),(0,d.jsxs)(`dl`,{className:`r-mini-dl mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[13px]`,children:[(0,d.jsx)(`dt`,{children:c.n}),(0,d.jsx)(`dd`,{children:i}),(0,d.jsx)(`dt`,{children:c.fmt}),(0,d.jsx)(`dd`,{children:a}),(0,d.jsx)(`dt`,{children:c.chance}),(0,d.jsx)(`dd`,{children:o}),(0,d.jsx)(`dt`,{children:c.scoring}),(0,d.jsx)(`dd`,{children:s})]})]})}function C({n:e,svg:t,caption:n,testId:i}){return(0,d.jsx)(a,{y:16,amount:.1,children:(0,d.jsxs)(`figure`,{className:`l-card overflow-hidden`,"data-testid":i,children:[(0,d.jsx)(`div`,{className:`r-fig px-5 pb-2 pt-6 sm:px-7`,dangerouslySetInnerHTML:{__html:t}}),(0,d.jsx)(`p`,{className:`r-note px-5 pb-2 sm:hidden`,children:r.swipe}),(0,d.jsxs)(`figcaption`,{className:`r-cap border-t px-5 py-3 sm:px-7`,style:{borderColor:`var(--l-line)`},children:[(0,d.jsxs)(`b`,{children:[`Figure `,e,`.`]}),` `,n]})]})})}var w={ranking:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 630" width="960" height="630" role="img" aria-label="Step-by-step accuracy of the 13 models with 95 per cent confidence intervals"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >Text accuracy, step by step, with 95 % confidence intervals</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >All 9,995 questions of the five text sets; bars are bootstrap intervals. Shaded: models that cannot be told apart.</text>
<circle cx="6.0" cy="65.5" r="6" class="med" />
<text x="18.0" y="70.0" class="fg2 t-tag" text-anchor="start" >Medical fine-tune</text>
<circle cx="158.4" cy="65.5" r="6" class="gen" />
<text x="170.4" y="70.0" class="fg2 t-tag" text-anchor="start" >General model, not medically validated</text>
<line x1="290.0" y1="86.0" x2="290.0" y2="560.0" class="ln" stroke-width="1" />
<text x="290.0" y="578.0" class="fg3 t-ax" text-anchor="middle" >30</text>
<line x1="394.0" y1="86.0" x2="394.0" y2="560.0" class="ln" stroke-width="1" />
<text x="394.0" y="578.0" class="fg3 t-ax" text-anchor="middle" >40</text>
<line x1="498.0" y1="86.0" x2="498.0" y2="560.0" class="ln" stroke-width="1" />
<text x="498.0" y="578.0" class="fg3 t-ax" text-anchor="middle" >50</text>
<line x1="602.0" y1="86.0" x2="602.0" y2="560.0" class="ln" stroke-width="1" />
<text x="602.0" y="578.0" class="fg3 t-ax" text-anchor="middle" >60</text>
<line x1="706.0" y1="86.0" x2="706.0" y2="560.0" class="ln" stroke-width="1" />
<text x="706.0" y="578.0" class="fg3 t-ax" text-anchor="middle" >70</text>
<line x1="810.0" y1="86.0" x2="810.0" y2="560.0" class="ln" stroke-width="1" />
<text x="810.0" y="578.0" class="fg3 t-ax" text-anchor="middle" >80</text>
<text x="550.0" y="598.0" class="fg2 t-ax" text-anchor="middle" >Accuracy, %</text>
<rect x="0.0" y="162.0" width="920.0" height="146.0" rx="10" class="band" />
<text x="914.0" y="179.0" class="fg2 t-tag" text-anchor="end" >within one point: tied</text>
<text x="0.0" y="111.0" class="fg t-lab" text-anchor="start" >Gemma-4-31B-it</text>
<text x="0.0" y="125.0" class="fg3 t-tag" text-anchor="start" >USA · Non-medical</text>
<line x1="767.0" y1="110.0" x2="783.1" y2="110.0" class="genS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="767.0" y1="104.0" x2="767.0" y2="116.0" class="genS" stroke-width="1.6" opacity=".7"/>
<line x1="783.1" y1="104.0" x2="783.1" y2="116.0" class="genS" stroke-width="1.6" opacity=".7"/>
<circle cx="775.1" cy="110.0" r="5.5" class="gen" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="795.1" y="114.5" class="fg t-num" text-anchor="start" >76.6</text>
<text x="831.1" y="114.5" class="fg3 t-tag" text-anchor="start" >75.9 to 77.4</text>
<text x="0.0" y="147.0" class="fg t-lab" text-anchor="start" >HuatuoGPT-3-27B</text>
<text x="0.0" y="161.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="710.5" y1="146.0" x2="727.4" y2="146.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="710.5" y1="140.0" x2="710.5" y2="152.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="727.4" y1="140.0" x2="727.4" y2="152.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="718.9" cy="146.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="739.4" y="150.5" class="fg t-num" text-anchor="start" >71.2</text>
<text x="775.4" y="150.5" class="fg3 t-tag" text-anchor="start" >70.4 to 72.1</text>
<text x="0.0" y="183.0" class="fg t-lab" text-anchor="start" >Qwen3.5-4B</text>
<text x="0.0" y="197.0" class="fg3 t-tag" text-anchor="start" >China · Non-medical</text>
<line x1="618.1" y1="182.0" x2="635.5" y2="182.0" class="genS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="618.1" y1="176.0" x2="618.1" y2="188.0" class="genS" stroke-width="1.6" opacity=".7"/>
<line x1="635.5" y1="176.0" x2="635.5" y2="188.0" class="genS" stroke-width="1.6" opacity=".7"/>
<circle cx="626.6" cy="182.0" r="5.5" class="gen" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="647.5" y="186.5" class="fg t-num" text-anchor="start" >62.4</text>
<text x="683.5" y="186.5" class="fg3 t-tag" text-anchor="start" >61.5 to 63.2</text>
<text x="0.0" y="219.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-text-it</text>
<text x="0.0" y="233.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="614.7" y1="218.0" x2="631.8" y2="218.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="614.7" y1="212.0" x2="614.7" y2="224.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="631.8" y1="212.0" x2="631.8" y2="224.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="623.3" cy="218.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="643.8" y="222.5" class="fg t-num" text-anchor="start" >62.0</text>
<text x="679.8" y="222.5" class="fg3 t-tag" text-anchor="start" >61.2 to 62.9</text>
<text x="0.0" y="255.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-it</text>
<text x="0.0" y="269.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="611.0" y1="254.0" x2="628.3" y2="254.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="611.0" y1="248.0" x2="611.0" y2="260.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="628.3" y1="248.0" x2="628.3" y2="260.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="619.6" cy="254.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="640.3" y="258.5" class="fg t-num" text-anchor="start" >61.7</text>
<text x="676.3" y="258.5" class="fg3 t-tag" text-anchor="start" >60.9 to 62.5</text>
<text x="0.0" y="291.0" class="fg t-lab" text-anchor="start" >Baichuan-M2-32B</text>
<text x="0.0" y="305.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="605.6" y1="290.0" x2="623.0" y2="290.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="605.6" y1="284.0" x2="605.6" y2="296.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="623.0" y1="284.0" x2="623.0" y2="296.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="614.6" cy="290.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="635.0" y="294.5" class="fg t-num" text-anchor="start" >61.2</text>
<text x="671.0" y="294.5" class="fg3 t-tag" text-anchor="start" >60.4 to 62.0</text>
<text x="0.0" y="327.0" class="fg t-lab" text-anchor="start" >Lingshu-32B</text>
<text x="0.0" y="341.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="574.1" y1="326.0" x2="592.1" y2="326.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="574.1" y1="320.0" x2="574.1" y2="332.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="592.1" y1="320.0" x2="592.1" y2="332.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="583.0" cy="326.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="604.1" y="330.5" class="fg t-num" text-anchor="start" >58.2</text>
<text x="640.1" y="330.5" class="fg3 t-tag" text-anchor="start" >57.3 to 59.0</text>
<text x="0.0" y="363.0" class="fg t-lab" text-anchor="start" >MedGemma-4B-it</text>
<text x="0.0" y="377.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="497.2" y1="362.0" x2="515.1" y2="362.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="497.2" y1="356.0" x2="497.2" y2="368.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="515.1" y1="356.0" x2="515.1" y2="368.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="506.2" cy="362.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="527.1" y="366.5" class="fg t-num" text-anchor="start" >50.8</text>
<text x="563.1" y="366.5" class="fg3 t-tag" text-anchor="start" >49.9 to 51.6</text>
<text x="0.0" y="399.0" class="fg t-lab" text-anchor="start" >Med42-8B (v2)</text>
<text x="0.0" y="413.0" class="fg3 t-tag" text-anchor="start" >UAE · Medical</text>
<line x1="486.2" y1="398.0" x2="504.9" y2="398.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="486.2" y1="392.0" x2="486.2" y2="404.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="504.9" y1="392.0" x2="504.9" y2="404.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="495.2" cy="398.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="516.9" y="402.5" class="fg t-num" text-anchor="start" >49.7</text>
<text x="552.9" y="402.5" class="fg3 t-tag" text-anchor="start" >48.9 to 50.7</text>
<text x="0.0" y="435.0" class="fg t-lab" text-anchor="start" >JSL-MedLlama-3-8B-v2.0</text>
<text x="0.0" y="449.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="482.3" y1="434.0" x2="500.5" y2="434.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="482.3" y1="428.0" x2="482.3" y2="440.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="500.5" y1="428.0" x2="500.5" y2="440.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="491.4" cy="434.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="512.5" y="438.5" class="fg t-num" text-anchor="start" >49.4</text>
<text x="548.5" y="438.5" class="fg3 t-tag" text-anchor="start" >48.5 to 50.2</text>
<text x="0.0" y="471.0" class="fg t-lab" text-anchor="start" >MedGemma-1.5-4B-it</text>
<text x="0.0" y="485.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="413.1" y1="470.0" x2="431.6" y2="470.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="413.1" y1="464.0" x2="413.1" y2="476.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="431.6" y1="464.0" x2="431.6" y2="476.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="422.4" cy="470.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="443.6" y="474.5" class="fg t-num" text-anchor="start" >42.7</text>
<text x="479.6" y="474.5" class="fg3 t-tag" text-anchor="start" >41.8 to 43.6</text>
<text x="0.0" y="507.0" class="fg t-lab" text-anchor="start" >OpenBioLLM-8B</text>
<text x="0.0" y="521.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="404.9" y1="506.0" x2="423.2" y2="506.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="404.9" y1="500.0" x2="404.9" y2="512.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="423.2" y1="500.0" x2="423.2" y2="512.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="414.2" cy="506.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="435.2" y="510.5" class="fg t-num" text-anchor="start" >41.9</text>
<text x="471.2" y="510.5" class="fg3 t-tag" text-anchor="start" >41.0 to 42.8</text>
<text x="0.0" y="543.0" class="fg t-lab" text-anchor="start" >MedLlama2-7B</text>
<text x="0.0" y="557.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="325.4" y1="542.0" x2="343.7" y2="542.0" class="medS" stroke-width="13" stroke-linecap="round" opacity=".22"/>
<line x1="325.4" y1="536.0" x2="325.4" y2="548.0" class="medS" stroke-width="1.6" opacity=".7"/>
<line x1="343.7" y1="536.0" x2="343.7" y2="548.0" class="medS" stroke-width="1.6" opacity=".7"/>
<circle cx="334.7" cy="542.0" r="5.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="355.7" y="546.5" class="fg t-num" text-anchor="start" >34.3</text>
<text x="391.7" y="546.5" class="fg3 t-tag" text-anchor="start" >33.4 to 35.2</text>
</svg>
`,reasoning:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 578" width="960" height="578" role="img" aria-label="Direct answer against step-by-step accuracy for each model"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >What reasoning adds</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Overall text accuracy with a one-letter answer (open dot) and when the model may reason first (filled dot).</text>
<circle cx="6.0" cy="65.5" r="6" class="bg" stroke="var(--l-fg-2,#475569)" stroke-width="2"/>
<text x="18.0" y="70.0" class="fg2 t-tag" text-anchor="start" >Direct answer</text>
<circle cx="126.0" cy="65.5" r="6" class="fg2" />
<text x="138.0" y="70.0" class="fg2 t-tag" text-anchor="start" >Step by step</text>
<line x1="300.0" y1="86.0" x2="300.0" y2="508.0" class="ln" stroke-width="1" />
<text x="300.0" y="526.0" class="fg3 t-ax" text-anchor="middle" >20</text>
<line x1="398.3" y1="86.0" x2="398.3" y2="508.0" class="ln" stroke-width="1" />
<text x="398.3" y="526.0" class="fg3 t-ax" text-anchor="middle" >30</text>
<line x1="496.7" y1="86.0" x2="496.7" y2="508.0" class="ln" stroke-width="1" />
<text x="496.7" y="526.0" class="fg3 t-ax" text-anchor="middle" >40</text>
<line x1="595.0" y1="86.0" x2="595.0" y2="508.0" class="ln" stroke-width="1" />
<text x="595.0" y="526.0" class="fg3 t-ax" text-anchor="middle" >50</text>
<line x1="693.3" y1="86.0" x2="693.3" y2="508.0" class="ln" stroke-width="1" />
<text x="693.3" y="526.0" class="fg3 t-ax" text-anchor="middle" >60</text>
<line x1="791.7" y1="86.0" x2="791.7" y2="508.0" class="ln" stroke-width="1" />
<text x="791.7" y="526.0" class="fg3 t-ax" text-anchor="middle" >70</text>
<line x1="890.0" y1="86.0" x2="890.0" y2="508.0" class="ln" stroke-width="1" />
<text x="890.0" y="526.0" class="fg3 t-ax" text-anchor="middle" >80</text>
<text x="595.0" y="546.0" class="fg2 t-ax" text-anchor="middle" >Accuracy, %</text>
<text x="0.0" y="109.0" class="fg t-lab" text-anchor="start" >Gemma-4-31B-it</text>
<text x="0.0" y="123.0" class="fg3 t-tag" text-anchor="start" >USA · Non-medical</text>
<line x1="685.8" y1="108.0" x2="856.9" y2="108.0" class="genS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="685.8" cy="108.0" r="6" class="bg" stroke="#7c5cf0" stroke-width="2.5"/>
<circle cx="856.9" cy="108.0" r="7" class="gen" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="868.9" y="112.5" class="fg t-num" text-anchor="start" >+17.4</text>
<text x="0.0" y="141.0" class="fg t-lab" text-anchor="start" >HuatuoGPT-3-27B</text>
<text x="0.0" y="155.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="752.8" y1="140.0" x2="803.8" y2="140.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="752.8" cy="140.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="803.8" cy="140.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="815.8" y="144.5" class="fg t-num" text-anchor="start" >+5.2</text>
<text x="0.0" y="173.0" class="fg t-lab" text-anchor="start" >Qwen3.5-4B</text>
<text x="0.0" y="187.0" class="fg3 t-tag" text-anchor="start" >China · Non-medical</text>
<line x1="625.5" y1="172.0" x2="716.7" y2="172.0" class="genS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="625.5" cy="172.0" r="6" class="bg" stroke="#7c5cf0" stroke-width="2.5"/>
<circle cx="716.7" cy="172.0" r="7" class="gen" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="728.7" y="176.5" class="fg t-num" text-anchor="start" >+9.3</text>
<text x="0.0" y="205.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-text-it</text>
<text x="0.0" y="219.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="399.1" y1="204.0" x2="713.5" y2="204.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="399.1" cy="204.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="713.5" cy="204.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="725.5" y="208.5" class="fg t-num" text-anchor="start" >+32.0</text>
<text x="0.0" y="237.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-it</text>
<text x="0.0" y="251.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="628.6" y1="236.0" x2="710.0" y2="236.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="628.6" cy="236.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="710.0" cy="236.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="722.0" y="240.5" class="fg t-num" text-anchor="start" >+8.3</text>
<text x="0.0" y="269.0" class="fg t-lab" text-anchor="start" >Baichuan-M2-32B †</text>
<text x="0.0" y="283.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="679.6" y1="268.0" x2="705.2" y2="268.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="679.6" cy="268.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="705.2" cy="268.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="717.2" y="272.5" class="fg t-num" text-anchor="start" >+2.6</text>
<text x="0.0" y="301.0" class="fg t-lab" text-anchor="start" >Lingshu-32B</text>
<text x="0.0" y="315.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="691.8" y1="300.0" x2="675.3" y2="300.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="691.8" cy="300.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="675.3" cy="300.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="703.8" y="304.5" class="fg2 t-num" text-anchor="start" >-1.7</text>
<text x="0.0" y="333.0" class="fg t-lab" text-anchor="start" >MedGemma-4B-it</text>
<text x="0.0" y="347.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="561.7" y1="332.0" x2="602.7" y2="332.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="561.7" cy="332.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="602.7" cy="332.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="614.7" y="336.5" class="fg t-num" text-anchor="start" >+4.2</text>
<text x="0.0" y="365.0" class="fg t-lab" text-anchor="start" >Med42-8B (v2)</text>
<text x="0.0" y="379.0" class="fg3 t-tag" text-anchor="start" >UAE · Medical</text>
<line x1="618.9" y1="364.0" x2="592.4" y2="364.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="618.9" cy="364.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="592.4" cy="364.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="630.9" y="368.5" class="fg2 t-num" text-anchor="start" >-2.7</text>
<text x="0.0" y="397.0" class="fg t-lab" text-anchor="start" >JSL-MedLlama-3-8B-v2.0</text>
<text x="0.0" y="411.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="565.1" y1="396.0" x2="588.9" y2="396.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="565.1" cy="396.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="588.9" cy="396.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="600.9" y="400.5" class="fg t-num" text-anchor="start" >+2.4</text>
<text x="0.0" y="429.0" class="fg t-lab" text-anchor="start" >MedGemma-1.5-4B-it</text>
<text x="0.0" y="443.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="396.8" y1="428.0" x2="523.5" y2="428.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="396.8" cy="428.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="523.5" cy="428.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="535.5" y="432.5" class="fg t-num" text-anchor="start" >+12.9</text>
<text x="0.0" y="461.0" class="fg t-lab" text-anchor="start" >OpenBioLLM-8B</text>
<text x="0.0" y="475.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="451.9" y1="460.0" x2="515.8" y2="460.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="451.9" cy="460.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="515.8" cy="460.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="527.8" y="464.5" class="fg t-num" text-anchor="start" >+6.5</text>
<text x="0.0" y="493.0" class="fg t-lab" text-anchor="start" >MedLlama2-7B</text>
<text x="0.0" y="507.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="380.6" y1="492.0" x2="440.6" y2="492.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".55"/>
<circle cx="380.6" cy="492.0" r="6" class="bg" stroke="#0e9aa7" stroke-width="2.5"/>
<circle cx="440.6" cy="492.0" r="7" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="452.6" y="496.5" class="fg t-num" text-anchor="start" >+6.1</text>
</svg>
`,published:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 686" width="960" height="686" role="img" aria-label="This run against the published scores"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >The harness reproduces the model cards</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Each dot is one model on one text set: published score across, this run up. On the line = identical; band = within 3 points.</text>
<line x1="60.0" y1="616.0" x2="60.0" y2="96.0" class="ln" stroke-width="1" />
<line x1="60.0" y1="616.0" x2="580.0" y2="616.0" class="ln" stroke-width="1" />
<text x="60.0" y="634.0" class="fg3 t-ax" text-anchor="middle" >0</text>
<text x="52.0" y="620.0" class="fg3 t-ax" text-anchor="end" >0</text>
<line x1="164.0" y1="616.0" x2="164.0" y2="96.0" class="ln" stroke-width="1" />
<line x1="60.0" y1="512.0" x2="580.0" y2="512.0" class="ln" stroke-width="1" />
<text x="164.0" y="634.0" class="fg3 t-ax" text-anchor="middle" >20</text>
<text x="52.0" y="516.0" class="fg3 t-ax" text-anchor="end" >20</text>
<line x1="268.0" y1="616.0" x2="268.0" y2="96.0" class="ln" stroke-width="1" />
<line x1="60.0" y1="408.0" x2="580.0" y2="408.0" class="ln" stroke-width="1" />
<text x="268.0" y="634.0" class="fg3 t-ax" text-anchor="middle" >40</text>
<text x="52.0" y="412.0" class="fg3 t-ax" text-anchor="end" >40</text>
<line x1="372.0" y1="616.0" x2="372.0" y2="96.0" class="ln" stroke-width="1" />
<line x1="60.0" y1="304.0" x2="580.0" y2="304.0" class="ln" stroke-width="1" />
<text x="372.0" y="634.0" class="fg3 t-ax" text-anchor="middle" >60</text>
<text x="52.0" y="308.0" class="fg3 t-ax" text-anchor="end" >60</text>
<line x1="476.0" y1="616.0" x2="476.0" y2="96.0" class="ln" stroke-width="1" />
<line x1="60.0" y1="200.0" x2="580.0" y2="200.0" class="ln" stroke-width="1" />
<text x="476.0" y="634.0" class="fg3 t-ax" text-anchor="middle" >80</text>
<text x="52.0" y="204.0" class="fg3 t-ax" text-anchor="end" >80</text>
<line x1="580.0" y1="616.0" x2="580.0" y2="96.0" class="ln" stroke-width="1" />
<line x1="60.0" y1="96.0" x2="580.0" y2="96.0" class="ln" stroke-width="1" />
<text x="580.0" y="634.0" class="fg3 t-ax" text-anchor="middle" >100</text>
<text x="52.0" y="100.0" class="fg3 t-ax" text-anchor="end" >100</text>
<polygon points="60.0,600.4 564.4,96.0 580.0,96.0 580.0,111.60000000000002 75.6,616.0 60.0,616.0" class="band"/>
<line x1="60.0" y1="616.0" x2="580.0" y2="96.0" class="ax" stroke-width="1.4" stroke-dasharray="5 5"/>
<text x="320.0" y="656.0" class="fg2 t-ax" text-anchor="middle" >Published score, %</text>
<text x="16.0" y="356.0" class="fg2 t-ax" text-anchor="middle" transform="rotate(-90 16.0 356.0)">This run, %</text>
<circle cx="516.0" cy="199.0" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="445.8" cy="243.9" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="459.4" cy="227.6" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="512.4" cy="153.8" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="193.6" cy="515.6" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="503.6" cy="183.8" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="425.0" cy="259.7" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="461.4" cy="216.1" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="508.2" cy="160.5" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="183.2" cy="505.9" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="448.4" cy="217.3" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="403.7" cy="289.8" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="464.6" cy="198.4" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="500.4" cy="179.1" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="178.0" cy="510.8" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="394.9" cy="272.5" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="349.6" cy="324.2" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="441.7" cy="221.8" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="424.0" cy="245.4" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="133.8" cy="540.9" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="386.6" cy="290.0" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="378.8" cy="311.2" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="454.2" cy="232.6" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="379.3" cy="310.0" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="378.2" cy="327.3" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="445.8" cy="219.2" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="463.5" cy="236.9" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="419.3" cy="372.1" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="371.0" cy="353.6" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="414.6" cy="299.3" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="421.9" cy="279.8" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="145.3" cy="563.0" r="6.5" class="med" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="366.8" cy="356.6" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="355.9" cy="366.5" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="445.3" cy="342.5" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="460.9" cy="265.1" r="6.5" class="warm" opacity=".9" stroke="var(--l-surface,#fff)" stroke-width="1.8"/>
<circle cx="626.0" cy="116.0" r="7" class="med" />
<text x="640.0" y="121.0" class="fg t-lab" text-anchor="start" >Generated answers on the card</text>
<text x="640.0" y="139.0" class="fg2 t-tag" text-anchor="start" >MedGemma 27B, 27B-text, 4B, 1.5-4B; Lingshu-32B</text>
<circle cx="626.0" cy="170.0" r="7" class="warm" />
<text x="640.0" y="175.0" class="fg t-lab" text-anchor="start" >Answer likelihood on the card</text>
<text x="640.0" y="193.0" class="fg2 t-tag" text-anchor="start" >Med42-8B, JSL-MedLlama-8B, OpenBioLLM-8B</text>
<text x="620.0" y="246.0" class="fg2 t-tag" text-anchor="start" >Mean difference, this run minus card</text>
<text x="620.0" y="270.0" class="fg t-tag" text-anchor="start" >MedGemma-27B-text-it</text>
<text x="930.0" y="270.0" class="fg t-num" text-anchor="end" >-3.4</text>
<text x="620.0" y="292.0" class="fg t-tag" text-anchor="start" >MedGemma-27B-it</text>
<text x="930.0" y="292.0" class="fg t-num" text-anchor="end" >-1.1</text>
<text x="620.0" y="314.0" class="fg t-tag" text-anchor="start" >Lingshu-32B</text>
<text x="930.0" y="314.0" class="fg t-num" text-anchor="end" >-0.4</text>
<text x="620.0" y="336.0" class="fg t-tag" text-anchor="start" >MedGemma-4B-it</text>
<text x="930.0" y="336.0" class="fg t-num" text-anchor="end" >+1.2</text>
<text x="620.0" y="358.0" class="fg t-tag" text-anchor="start" >Med42-8B (v2)</text>
<text x="930.0" y="358.0" class="fg t-num" text-anchor="end" >-1.6</text>
<text x="620.0" y="380.0" class="fg t-tag" text-anchor="start" >JSL-MedLlama-3-8B-v2.0</text>
<text x="930.0" y="380.0" class="fg t-num" text-anchor="end" >-2.7</text>
<text x="620.0" y="402.0" class="fg t-tag" text-anchor="start" >MedGemma-1.5-4B-it</text>
<text x="930.0" y="402.0" class="fg t-num" text-anchor="end" >-10.0</text>
<text x="620.0" y="424.0" class="fg t-tag" text-anchor="start" >OpenBioLLM-8B</text>
<text x="930.0" y="424.0" class="fg t-num" text-anchor="end" >-12.3</text>
</svg>
`,q4:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 442" width="960" height="442" role="img" aria-label="The same weights at 4 bits and at full precision"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >Full precision against the earlier 4-bit run</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Mean of the five text sets, the same models: 4-bit weights (Sept. 2026), then bf16 direct, then bf16 step by step.</text>
<circle cx="6.0" cy="65.5" r="6" class="fg3" />
<text x="18.0" y="70.0" class="fg2 t-tag" text-anchor="start" >4-bit (Q4_K_M)</text>
<circle cx="156.0" cy="65.5" r="6" class="fg2" />
<text x="168.0" y="70.0" class="fg2 t-tag" text-anchor="start" >bf16, direct</text>
<circle cx="276.0" cy="65.5" r="6" class="med" />
<text x="288.0" y="70.0" class="fg2 t-tag" text-anchor="start" >bf16, step by step</text>
<line x1="300.0" y1="86.0" x2="300.0" y2="372.0" class="ln" stroke-width="1" />
<text x="300.0" y="390.0" class="fg3 t-ax" text-anchor="middle" >10</text>
<line x1="384.3" y1="86.0" x2="384.3" y2="372.0" class="ln" stroke-width="1" />
<text x="384.3" y="390.0" class="fg3 t-ax" text-anchor="middle" >20</text>
<line x1="468.6" y1="86.0" x2="468.6" y2="372.0" class="ln" stroke-width="1" />
<text x="468.6" y="390.0" class="fg3 t-ax" text-anchor="middle" >30</text>
<line x1="552.9" y1="86.0" x2="552.9" y2="372.0" class="ln" stroke-width="1" />
<text x="552.9" y="390.0" class="fg3 t-ax" text-anchor="middle" >40</text>
<line x1="637.1" y1="86.0" x2="637.1" y2="372.0" class="ln" stroke-width="1" />
<text x="637.1" y="390.0" class="fg3 t-ax" text-anchor="middle" >50</text>
<line x1="721.4" y1="86.0" x2="721.4" y2="372.0" class="ln" stroke-width="1" />
<text x="721.4" y="390.0" class="fg3 t-ax" text-anchor="middle" >60</text>
<line x1="805.7" y1="86.0" x2="805.7" y2="372.0" class="ln" stroke-width="1" />
<text x="805.7" y="390.0" class="fg3 t-ax" text-anchor="middle" >70</text>
<line x1="890.0" y1="86.0" x2="890.0" y2="372.0" class="ln" stroke-width="1" />
<text x="890.0" y="390.0" class="fg3 t-ax" text-anchor="middle" >80</text>
<text x="595.0" y="410.0" class="fg2 t-ax" text-anchor="middle" >Mean accuracy over the five sets, %</text>
<text x="0.0" y="113.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-it</text>
<text x="0.0" y="127.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="717.2" y1="112.0" x2="784.3" y2="112.0" class="ln2" stroke-width="3" stroke-linecap="round"/>
<path d="M727.8,112.0 L784.3,112.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>
<circle cx="727.8" cy="112.0" r="6.5" class="fg3" />
<circle cx="717.2" cy="112.0" r="6.5" class="fg2" />
<circle cx="784.3" cy="112.0" r="7.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="796.3" y="116.5" class="fg t-num" text-anchor="start" >+6.7</text>
<text x="0.0" y="153.0" class="fg t-lab" text-anchor="start" >MedGemma-4B-it</text>
<text x="0.0" y="167.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="627.0" y1="152.0" x2="693.9" y2="152.0" class="ln2" stroke-width="3" stroke-linecap="round"/>
<path d="M627.0,152.0 L693.9,152.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>
<circle cx="627.0" cy="152.0" r="6.5" class="fg3" />
<circle cx="654.4" cy="152.0" r="6.5" class="fg2" />
<circle cx="693.9" cy="152.0" r="7.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="705.9" y="156.5" class="fg t-num" text-anchor="start" >+7.9</text>
<text x="0.0" y="193.0" class="fg t-lab" text-anchor="start" >JSL-MedLlama-3-8B-v2.0</text>
<text x="0.0" y="207.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="427.3" y1="192.0" x2="681.1" y2="192.0" class="ln2" stroke-width="3" stroke-linecap="round"/>
<path d="M427.3,192.0 L681.1,192.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>
<circle cx="427.3" cy="192.0" r="6.5" class="fg3" />
<circle cx="648.3" cy="192.0" r="6.5" class="fg2" />
<circle cx="681.1" cy="192.0" r="7.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="693.1" y="196.5" class="fg t-num" text-anchor="start" >+30.1</text>
<text x="0.0" y="233.0" class="fg t-lab" text-anchor="start" >Med42-8B (v2)</text>
<text x="0.0" y="247.0" class="fg3 t-tag" text-anchor="start" >UAE · Medical</text>
<line x1="665.4" y1="232.0" x2="700.2" y2="232.0" class="ln2" stroke-width="3" stroke-linecap="round"/>
<path d="M684.3,232.0 L665.4,232.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>
<circle cx="684.3" cy="232.0" r="6.5" class="fg3" />
<circle cx="700.2" cy="232.0" r="6.5" class="fg2" />
<circle cx="665.4" cy="232.0" r="7.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="712.2" y="236.5" class="fg t-num" text-anchor="start" >-2.2</text>
<text x="0.0" y="273.0" class="fg t-lab" text-anchor="start" >MedGemma-1.5-4B-it</text>
<text x="0.0" y="287.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="475.0" y1="272.0" x2="608.7" y2="272.0" class="ln2" stroke-width="3" stroke-linecap="round"/>
<path d="M475.0,272.0 L608.7,272.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>
<circle cx="475.0" cy="272.0" r="6.5" class="fg3" />
<circle cx="481.6" cy="272.0" r="6.5" class="fg2" />
<circle cx="608.7" cy="272.0" r="7.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="620.7" y="276.5" class="fg t-num" text-anchor="start" >+15.9</text>
<text x="0.0" y="313.0" class="fg t-lab" text-anchor="start" >OpenBioLLM-8B</text>
<text x="0.0" y="327.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="429.3" y1="312.0" x2="603.0" y2="312.0" class="ln2" stroke-width="3" stroke-linecap="round"/>
<path d="M429.3,312.0 L603.0,312.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>
<circle cx="429.3" cy="312.0" r="6.5" class="fg3" />
<circle cx="545.6" cy="312.0" r="6.5" class="fg2" />
<circle cx="603.0" cy="312.0" r="7.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="615.0" y="316.5" class="fg t-num" text-anchor="start" >+20.6</text>
<text x="0.0" y="353.0" class="fg t-lab" text-anchor="start" >MedLlama2-7B</text>
<text x="0.0" y="367.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="466.9" y1="352.0" x2="555.9" y2="352.0" class="ln2" stroke-width="3" stroke-linecap="round"/>
<path d="M466.9,352.0 L555.9,352.0" class="medS" stroke-width="3.5" stroke-linecap="round" opacity=".45"/>
<circle cx="466.9" cy="352.0" r="6.5" class="fg3" />
<circle cx="488.9" cy="352.0" r="6.5" class="fg2" />
<circle cx="555.9" cy="352.0" r="7.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="567.9" y="356.5" class="fg t-num" text-anchor="start" >+10.6</text>
</svg>
`,images:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 476" width="960" height="476" role="img" aria-label="Image question accuracy of the seven vision models"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >Image questions: who leads where</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Accuracy, %; darker = higher, ringed = best in the column. Direct protocol unless marked CoT; OmniMedVQA uses the first-token score.</text>
<text x="300.7" y="114.0" class="fg2 t-tag" text-anchor="middle" >VQA-RAD</text>
<text x="402.1" y="114.0" class="fg2 t-tag" text-anchor="middle" >SLAKE</text>
<text x="503.6" y="114.0" class="fg2 t-tag" text-anchor="middle" >PathVQA</text>
<text x="605.0" y="114.0" class="fg2 t-tag" text-anchor="middle" >PMC-VQA</text>
<text x="706.4" y="100.0" class="fg2 t-tag" text-anchor="middle" >PMC-VQA</text>
<text x="706.4" y="115.0" class="fg3 t-tag" text-anchor="middle" >CoT</text>
<text x="807.9" y="100.0" class="fg2 t-tag" text-anchor="middle" >MedXpertQA-MM</text>
<text x="807.9" y="115.0" class="fg3 t-tag" text-anchor="middle" >CoT</text>
<text x="909.3" y="114.0" class="fg2 t-tag" text-anchor="middle" >OmniMedVQA</text>
<text x="0.0" y="151.0" class="fg t-lab" text-anchor="start" >HuatuoGPT-3-27B</text>
<text x="0.0" y="165.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<rect x="253.0" y="131.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.54"/>
<text x="300.7" y="155.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">54.5</text>
<rect x="354.4" y="131.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.59"/>
<text x="402.1" y="155.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">60.3</text>
<rect x="455.9" y="131.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.41"/>
<text x="503.6" y="155.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">38.9</text>
<rect x="557.3" y="131.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.58"/>
<text x="605.0" y="155.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">59.3</text>
<rect x="658.7" y="131.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.61"/>
<text x="706.4" y="155.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">62.7</text>
<rect x="760.1" y="131.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.50"/>
<text x="807.9" y="155.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">49.7</text>
<rect x="861.6" y="131.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.78"/>
<rect x="859.6" y="129.0" width="99.4" height="42.0" rx="10" class="" fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"/>
<text x="909.3" y="155.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="800">82.9</text>
<text x="0.0" y="195.0" class="fg t-lab" text-anchor="start" >Lingshu-32B</text>
<text x="0.0" y="209.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<rect x="253.0" y="175.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.65"/>
<rect x="251.0" y="173.0" width="99.4" height="42.0" rx="10" class="" fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"/>
<text x="300.7" y="199.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="800">67.4</text>
<rect x="354.4" y="175.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.80"/>
<rect x="352.4" y="173.0" width="99.4" height="42.0" rx="10" class="" fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"/>
<text x="402.1" y="199.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="800">84.9</text>
<rect x="455.9" y="175.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.59"/>
<rect x="453.9" y="173.0" width="99.4" height="42.0" rx="10" class="" fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"/>
<text x="503.6" y="199.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="800">59.9</text>
<rect x="557.3" y="175.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.63"/>
<rect x="555.3" y="173.0" width="99.4" height="42.0" rx="10" class="" fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"/>
<text x="605.0" y="199.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="800">64.9</text>
<rect x="658.7" y="175.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.59"/>
<text x="706.4" y="199.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">60.1</text>
<rect x="760.1" y="175.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.35"/>
<text x="807.9" y="199.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">31.5</text>
<rect x="861.6" y="175.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.78"/>
<text x="909.3" y="199.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">82.4</text>
<text x="0.0" y="239.0" class="fg t-lab" text-anchor="start" >Gemma-4-31B-it</text>
<text x="0.0" y="253.0" class="fg3 t-tag" text-anchor="start" >USA · Non-medical</text>
<rect x="253.0" y="219.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.52"/>
<text x="300.7" y="243.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">51.4</text>
<rect x="354.4" y="219.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.52"/>
<text x="402.1" y="243.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">51.5</text>
<rect x="455.9" y="219.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.39"/>
<text x="503.6" y="243.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">36.8</text>
<rect x="557.3" y="219.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.46"/>
<text x="605.0" y="243.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">45.1</text>
<rect x="658.7" y="219.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.64"/>
<rect x="656.7" y="217.0" width="99.4" height="42.0" rx="10" class="" fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"/>
<text x="706.4" y="243.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="800">66.2</text>
<rect x="760.1" y="219.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.55"/>
<rect x="758.1" y="217.0" width="99.4" height="42.0" rx="10" class="" fill="none" stroke="var(--l-fg,#0f172a)" stroke-width="2.2"/>
<text x="807.9" y="243.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="800">55.5</text>
<rect x="861.6" y="219.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.77"/>
<text x="909.3" y="243.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">81.5</text>
<text x="0.0" y="283.0" class="fg t-lab" text-anchor="start" >Qwen3.5-4B</text>
<text x="0.0" y="297.0" class="fg3 t-tag" text-anchor="start" >China · Non-medical</text>
<rect x="253.0" y="263.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.55"/>
<text x="300.7" y="287.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">55.6</text>
<rect x="354.4" y="263.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.59"/>
<text x="402.1" y="287.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">59.6</text>
<rect x="455.9" y="263.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.42"/>
<text x="503.6" y="287.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">39.8</text>
<rect x="557.3" y="263.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.22"/>
<text x="605.0" y="287.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">16.2</text>
<rect x="658.7" y="263.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.59"/>
<text x="706.4" y="287.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">60.0</text>
<rect x="760.1" y="263.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.38"/>
<text x="807.9" y="287.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">35.5</text>
<rect x="861.6" y="263.0" width="95.4" height="38.0" rx="8" class="" fill="#7c5cf0" fill-opacity="0.71"/>
<text x="909.3" y="287.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">74.2</text>
<text x="0.0" y="327.0" class="fg t-lab" text-anchor="start" >MedGemma-4B-it</text>
<text x="0.0" y="341.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<rect x="253.0" y="307.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.56"/>
<text x="300.7" y="331.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">56.8</text>
<rect x="354.4" y="307.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.53"/>
<text x="402.1" y="331.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">52.8</text>
<rect x="455.9" y="307.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.36"/>
<text x="503.6" y="331.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">33.1</text>
<rect x="557.3" y="307.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.47"/>
<text x="605.0" y="331.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">46.2</text>
<rect x="658.7" y="307.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.48"/>
<text x="706.4" y="331.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">46.5</text>
<rect x="760.1" y="307.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.30"/>
<text x="807.9" y="331.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">25.4</text>
<rect x="861.6" y="307.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.68"/>
<text x="909.3" y="331.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">70.4</text>
<text x="0.0" y="371.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-it</text>
<text x="0.0" y="385.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<rect x="253.0" y="351.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.51"/>
<text x="300.7" y="375.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">50.5</text>
<rect x="354.4" y="351.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.50"/>
<text x="402.1" y="375.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">50.0</text>
<rect x="455.9" y="351.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.35"/>
<text x="503.6" y="375.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">32.1</text>
<rect x="557.3" y="351.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.40"/>
<text x="605.0" y="375.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">38.2</text>
<rect x="658.7" y="351.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.48"/>
<text x="706.4" y="375.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">47.1</text>
<rect x="760.1" y="351.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.36"/>
<text x="807.9" y="375.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">33.2</text>
<rect x="861.6" y="351.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.66"/>
<text x="909.3" y="375.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">68.6</text>
<text x="0.0" y="415.0" class="fg t-lab" text-anchor="start" >MedGemma-1.5-4B-it</text>
<text x="0.0" y="429.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<rect x="253.0" y="395.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.43"/>
<text x="300.7" y="419.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">41.2</text>
<rect x="354.4" y="395.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.38"/>
<text x="402.1" y="419.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">35.7</text>
<rect x="455.9" y="395.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.32"/>
<text x="503.6" y="419.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">27.7</text>
<rect x="557.3" y="395.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.23"/>
<text x="605.0" y="419.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">17.6</text>
<rect x="658.7" y="395.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.46"/>
<text x="706.4" y="419.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">45.0</text>
<rect x="760.1" y="395.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.16"/>
<text x="807.9" y="419.0" class="t-num" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">9.6</text>
<rect x="861.6" y="395.0" width="95.4" height="38.0" rx="8" class="" fill="#0e9aa7" fill-opacity="0.66"/>
<text x="909.3" y="419.0" class="t-num" text-anchor="middle" fill="#ffffff" font-weight="600">68.2</text>
</svg>
`,oncology:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 578" width="960" height="578" role="img" aria-label="Accuracy on questions about cancer against the other questions"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >Cancer questions against the rest (674 of the MedQA, MedMCQA and MedXpertQA questions)</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Step by step. Open dot: the other questions of the same sets; filled dot: questions that mention cancer, with its 95 % interval.</text>
<line x1="300.0" y1="86.0" x2="300.0" y2="508.0" class="ln" stroke-width="1" />
<text x="300.0" y="526.0" class="fg3 t-ax" text-anchor="middle" >20</text>
<line x1="398.3" y1="86.0" x2="398.3" y2="508.0" class="ln" stroke-width="1" />
<text x="398.3" y="526.0" class="fg3 t-ax" text-anchor="middle" >30</text>
<line x1="496.7" y1="86.0" x2="496.7" y2="508.0" class="ln" stroke-width="1" />
<text x="496.7" y="526.0" class="fg3 t-ax" text-anchor="middle" >40</text>
<line x1="595.0" y1="86.0" x2="595.0" y2="508.0" class="ln" stroke-width="1" />
<text x="595.0" y="526.0" class="fg3 t-ax" text-anchor="middle" >50</text>
<line x1="693.3" y1="86.0" x2="693.3" y2="508.0" class="ln" stroke-width="1" />
<text x="693.3" y="526.0" class="fg3 t-ax" text-anchor="middle" >60</text>
<line x1="791.7" y1="86.0" x2="791.7" y2="508.0" class="ln" stroke-width="1" />
<text x="791.7" y="526.0" class="fg3 t-ax" text-anchor="middle" >70</text>
<line x1="890.0" y1="86.0" x2="890.0" y2="508.0" class="ln" stroke-width="1" />
<text x="890.0" y="526.0" class="fg3 t-ax" text-anchor="middle" >80</text>
<text x="595.0" y="546.0" class="fg2 t-ax" text-anchor="middle" >Accuracy, %</text>
<text x="0.0" y="109.0" class="fg t-lab" text-anchor="start" >Gemma-4-31B-it</text>
<text x="0.0" y="123.0" class="fg3 t-tag" text-anchor="start" >USA · Non-medical</text>
<line x1="800.7" y1="108.0" x2="860.5" y2="108.0" class="genS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="827.3" cy="108.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="831.4" cy="108.0" r="6.5" class="gen" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="870.5" y="112.5" class="fg t-num" text-anchor="start" >+0.4</text>
<text x="0.0" y="141.0" class="fg t-lab" text-anchor="start" >HuatuoGPT-3-27B</text>
<text x="0.0" y="155.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="735.0" y1="140.0" x2="797.8" y2="140.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="762.0" cy="140.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="767.2" cy="140.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="807.8" y="144.5" class="fg t-num" text-anchor="start" >+0.5</text>
<text x="0.0" y="173.0" class="fg t-lab" text-anchor="start" >Qwen3.5-4B</text>
<text x="0.0" y="187.0" class="fg3 t-tag" text-anchor="start" >China · Non-medical</text>
<line x1="609.6" y1="172.0" x2="673.8" y2="172.0" class="genS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="662.9" cy="172.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="641.7" cy="172.0" r="6.5" class="gen" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="683.8" y="176.5" class="fg2 t-num" text-anchor="start" >-2.1</text>
<text x="0.0" y="205.0" class="fg t-lab" text-anchor="start" >Baichuan-M2-32B</text>
<text x="0.0" y="219.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="611.0" y1="204.0" x2="672.4" y2="204.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="660.0" cy="204.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="641.7" cy="204.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="682.4" y="208.5" class="fg2 t-num" text-anchor="start" >-1.9</text>
<text x="0.0" y="237.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-it</text>
<text x="0.0" y="251.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="589.2" y1="236.0" x2="653.3" y2="236.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="659.2" cy="236.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="621.3" cy="236.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="669.2" y="240.5" class="fg2 t-num" text-anchor="start" >-3.9</text>
<text x="0.0" y="269.0" class="fg t-lab" text-anchor="start" >Lingshu-32B</text>
<text x="0.0" y="283.0" class="fg3 t-tag" text-anchor="start" >China · Medical</text>
<line x1="567.3" y1="268.0" x2="631.5" y2="268.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="614.1" cy="268.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="599.4" cy="268.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="641.5" y="272.5" class="fg2 t-num" text-anchor="start" >-1.5</text>
<text x="0.0" y="301.0" class="fg t-lab" text-anchor="start" >MedGemma-27B-text-it</text>
<text x="0.0" y="315.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="567.3" y1="300.0" x2="628.5" y2="300.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="667.4" cy="300.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="598.0" cy="300.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="677.4" y="304.5" class="fg2 t-num" text-anchor="start" >-7.1</text>
<text x="0.0" y="333.0" class="fg t-lab" text-anchor="start" >Med42-8B (v2)</text>
<text x="0.0" y="347.0" class="fg3 t-tag" text-anchor="start" >UAE · Medical</text>
<line x1="494.3" y1="332.0" x2="557.1" y2="332.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="551.9" cy="332.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="526.5" cy="332.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="567.1" y="336.5" class="fg2 t-num" text-anchor="start" >-2.6</text>
<text x="0.0" y="365.0" class="fg t-lab" text-anchor="start" >MedGemma-4B-it</text>
<text x="0.0" y="379.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="469.5" y1="364.0" x2="536.7" y2="364.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="547.5" cy="364.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="504.5" cy="364.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="557.5" y="368.5" class="fg2 t-num" text-anchor="start" >-4.4</text>
<text x="0.0" y="397.0" class="fg t-lab" text-anchor="start" >JSL-MedLlama-3-8B-v2.0</text>
<text x="0.0" y="411.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="438.8" y1="396.0" x2="500.2" y2="396.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="528.5" cy="396.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="469.5" cy="396.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="538.5" y="400.5" class="fg2 t-num" text-anchor="start" >-6.0</text>
<text x="0.0" y="429.0" class="fg t-lab" text-anchor="start" >MedGemma-1.5-4B-it</text>
<text x="0.0" y="443.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="401.0" y1="428.0" x2="462.2" y2="428.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="475.0" cy="428.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="430.1" cy="428.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="485.0" y="432.5" class="fg2 t-num" text-anchor="start" >-4.6</text>
<text x="0.0" y="461.0" class="fg t-lab" text-anchor="start" >OpenBioLLM-8B</text>
<text x="0.0" y="475.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="379.1" y1="460.0" x2="443.3" y2="460.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="473.1" cy="460.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="412.6" cy="460.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="483.1" y="464.5" class="fg2 t-num" text-anchor="start" >-6.2</text>
<text x="0.0" y="493.0" class="fg t-lab" text-anchor="start" >MedLlama2-7B</text>
<text x="0.0" y="507.0" class="fg3 t-tag" text-anchor="start" >USA · Medical</text>
<line x1="323.6" y1="492.0" x2="386.3" y2="492.0" class="medS" stroke-width="3" stroke-linecap="round" opacity=".35"/>
<circle cx="379.5" cy="492.0" r="5.5" class="bg" stroke="var(--l-fg-3,#94a3b8)" stroke-width="2"/>
<circle cx="354.3" cy="492.0" r="6.5" class="med" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="396.3" y="496.5" class="fg2 t-num" text-anchor="start" >-2.6</text>
</svg>
`,size:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 582" width="960" height="582" role="img" aria-label="Model size against step-by-step accuracy"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >Newer models beat bigger ones</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Parameters (log scale) against overall step-by-step accuracy. Ring: the model was also in the earlier 4-bit report.</text>
<circle cx="6.0" cy="65.5" r="6" class="med" />
<text x="18.0" y="70.0" class="fg2 t-tag" text-anchor="start" >Medical fine-tune</text>
<circle cx="158.4" cy="65.5" r="6" class="gen" />
<text x="170.4" y="70.0" class="fg2 t-tag" text-anchor="start" >General model, not medically validated</text>
<line x1="147.7" y1="512.0" x2="147.7" y2="92.0" class="ln" stroke-width="1" />
<text x="147.7" y="530.0" class="fg3 t-ax" text-anchor="middle" >4B</text>
<line x1="359.1" y1="512.0" x2="359.1" y2="92.0" class="ln" stroke-width="1" />
<text x="359.1" y="530.0" class="fg3 t-ax" text-anchor="middle" >8B</text>
<line x1="570.5" y1="512.0" x2="570.5" y2="92.0" class="ln" stroke-width="1" />
<text x="570.5" y="530.0" class="fg3 t-ax" text-anchor="middle" >16B</text>
<line x1="781.9" y1="512.0" x2="781.9" y2="92.0" class="ln" stroke-width="1" />
<text x="781.9" y="530.0" class="fg3 t-ax" text-anchor="middle" >32B</text>
<line x1="60.0" y1="512.0" x2="930.0" y2="512.0" class="ln" stroke-width="1" />
<text x="50.0" y="516.0" class="fg3 t-ax" text-anchor="end" >30</text>
<line x1="60.0" y1="428.0" x2="930.0" y2="428.0" class="ln" stroke-width="1" />
<text x="50.0" y="432.0" class="fg3 t-ax" text-anchor="end" >40</text>
<line x1="60.0" y1="344.0" x2="930.0" y2="344.0" class="ln" stroke-width="1" />
<text x="50.0" y="348.0" class="fg3 t-ax" text-anchor="end" >50</text>
<line x1="60.0" y1="260.0" x2="930.0" y2="260.0" class="ln" stroke-width="1" />
<text x="50.0" y="264.0" class="fg3 t-ax" text-anchor="end" >60</text>
<line x1="60.0" y1="176.0" x2="930.0" y2="176.0" class="ln" stroke-width="1" />
<text x="50.0" y="180.0" class="fg3 t-ax" text-anchor="end" >70</text>
<line x1="60.0" y1="92.0" x2="930.0" y2="92.0" class="ln" stroke-width="1" />
<text x="50.0" y="96.0" class="fg3 t-ax" text-anchor="end" >80</text>
<text x="482.8" y="552.0" class="fg2 t-ax" text-anchor="middle" >Parameters</text>
<circle cx="772.2" cy="120.3" r="7.5" class="gen" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="754.2" y="124.8" class="fg t-tag" text-anchor="end" >Gemma-4-31B-it</text>
<circle cx="730.1" cy="165.6" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="712.1" y="170.1" class="fg t-tag" text-anchor="end" >HuatuoGPT-3-27B</text>
<circle cx="147.7" cy="240.1" r="7.5" class="gen" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="165.7" y="244.6" class="fg t-tag" text-anchor="start" >Qwen3.5-4B</text>
<circle cx="730.1" cy="242.8" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="712.1" y="239.3" class="fg t-tag" text-anchor="end" >MedGemma-27B-text-it</text>
<circle cx="730.1" cy="245.8" r="12.5" class="" fill="none" stroke="#0e9aa7" stroke-width="1.6" opacity=".5"/>
<circle cx="730.1" cy="245.8" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="712.1" y="260.3" class="fg t-tag" text-anchor="end" >MedGemma-27B-it</text>
<circle cx="781.9" cy="249.8" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="799.9" y="250.3" class="fg t-tag" text-anchor="start" >Baichuan-M2-32B</text>
<circle cx="781.9" cy="275.4" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="799.9" y="281.9" class="fg t-tag" text-anchor="start" >Lingshu-32B</text>
<circle cx="147.7" cy="337.4" r="12.5" class="" fill="none" stroke="#0e9aa7" stroke-width="1.6" opacity=".5"/>
<circle cx="147.7" cy="337.4" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="165.7" y="341.9" class="fg t-tag" text-anchor="start" >MedGemma-4B-it</text>
<circle cx="359.1" cy="346.2" r="12.5" class="" fill="none" stroke="#0e9aa7" stroke-width="1.6" opacity=".5"/>
<circle cx="359.1" cy="346.2" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="377.1" y="343.7" class="fg t-tag" text-anchor="start" >Med42-8B (v2)</text>
<circle cx="359.1" cy="349.3" r="12.5" class="" fill="none" stroke="#0e9aa7" stroke-width="1.6" opacity=".5"/>
<circle cx="359.1" cy="349.3" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="377.1" y="362.8" class="fg t-tag" text-anchor="start" >JSL-MedLlama-3-8B-v2.0</text>
<circle cx="147.7" cy="405.0" r="12.5" class="" fill="none" stroke="#0e9aa7" stroke-width="1.6" opacity=".5"/>
<circle cx="147.7" cy="405.0" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="165.7" y="409.5" class="fg t-tag" text-anchor="start" >MedGemma-1.5-4B-it</text>
<circle cx="359.1" cy="411.7" r="12.5" class="" fill="none" stroke="#0e9aa7" stroke-width="1.6" opacity=".5"/>
<circle cx="359.1" cy="411.7" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="377.1" y="416.2" class="fg t-tag" text-anchor="start" >OpenBioLLM-8B</text>
<circle cx="318.4" cy="475.9" r="12.5" class="" fill="none" stroke="#0e9aa7" stroke-width="1.6" opacity=".5"/>
<circle cx="318.4" cy="475.9" r="7.5" class="med" opacity=".95" stroke="var(--l-surface,#fff)" stroke-width="2"/>
<text x="336.4" y="480.4" class="fg t-tag" text-anchor="start" >MedLlama2-7B</text>
</svg>
`,grounding:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 466" width="960" height="466" role="img" aria-label="Ask-the-Case-File probes and what the grounding layer removed"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >476 questions to the Case File: right answers, and what grounding removed</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Shipped pipeline (Gemma-4-31B-it, non-medical, with the verbatim-quote check). Bar length: probes; teal: right answer.</text>
<rect x="0.0" y="61.0" width="12.0" height="12.0" rx="3" class="med" />
<text x="18.0" y="71.0" class="fg2 t-tag" text-anchor="start" >Right answer</text>
<rect x="130.0" y="61.0" width="12.0" height="12.0" rx="3" class="neu" />
<text x="148.0" y="71.0" class="fg2 t-tag" text-anchor="start" >Missed</text>
<rect x="230.0" y="61.0" width="12.0" height="12.0" rx="3" class="bad" />
<text x="248.0" y="71.0" class="fg2 t-tag" text-anchor="start" >Fabricated value shown</text>
<text x="0.0" y="114.0" class="fg t-lab" text-anchor="start" >Answerable</text>
<text x="0.0" y="129.0" class="fg3 t-tag" text-anchor="start" >the value, with its quote</text>
<rect x="250.0" y="104.0" width="322.3" height="20.0" rx="6" class="neu" />
<rect x="250.0" y="104.0" width="319.6" height="20.0" rx="6" class="med" />
<text x="582.3" y="119.0" class="fg t-num" text-anchor="start" >117 of 118</text>
<text x="0.0" y="160.0" class="fg t-lab" text-anchor="start" >Not in the file (trap)</text>
<text x="0.0" y="175.0" class="fg3 t-tag" text-anchor="start" >said “not documented”, no value</text>
<rect x="250.0" y="150.0" width="560.0" height="20.0" rx="6" class="neu" />
<rect x="250.0" y="150.0" width="560.0" height="20.0" rx="6" class="med" />
<text x="820.0" y="165.0" class="fg t-num" text-anchor="start" >205 of 205</text>
<text x="0.0" y="206.0" class="fg t-lab" text-anchor="start" >Out of scope</text>
<text x="0.0" y="221.0" class="fg3 t-tag" text-anchor="start" >declined</text>
<rect x="250.0" y="196.0" width="87.4" height="20.0" rx="6" class="neu" />
<rect x="250.0" y="196.0" width="87.4" height="20.0" rx="6" class="med" />
<text x="347.4" y="211.0" class="fg t-num" text-anchor="start" >32 of 32</text>
<text x="0.0" y="252.0" class="fg t-lab" text-anchor="start" >Documented after all</text>
<text x="0.0" y="267.0" class="fg3 t-tag" text-anchor="start" >answered with verified quotes</text>
<rect x="250.0" y="242.0" width="174.8" height="20.0" rx="6" class="neu" />
<rect x="250.0" y="242.0" width="174.8" height="20.0" rx="6" class="med" />
<text x="434.8" y="257.0" class="fg t-num" text-anchor="start" >64 of 64</text>
<text x="0.0" y="298.0" class="fg t-lab" text-anchor="start" >Hand-written release set</text>
<text x="0.0" y="313.0" class="fg3 t-tag" text-anchor="start" >the 57 gate probes</text>
<rect x="250.0" y="288.0" width="155.7" height="20.0" rx="6" class="neu" />
<rect x="250.0" y="288.0" width="155.7" height="20.0" rx="6" class="med" />
<text x="415.7" y="303.0" class="fg t-num" text-anchor="start" >57 of 57</text>
<text x="0.0" y="360.0" class="fg t-lab" text-anchor="start" >The grounding layer removed 5 statements in all, reviewed by hand against the documents:</text>
<rect x="0.0" y="380.0" width="187.0" height="28.0" rx="14" class="neu" opacity=".7"/>
<text x="93.5" y="398.5" class="t-tag" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">true, quote did not match</text>
<rect x="197.0" y="380.0" width="152.0" height="28.0" rx="14" class="neu" opacity=".7"/>
<text x="273.0" y="398.5" class="t-tag" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">statement of absence</text>
<rect x="359.0" y="380.0" width="187.0" height="28.0" rx="14" class="neu" opacity=".7"/>
<text x="452.5" y="398.5" class="t-tag" text-anchor="middle" fill="var(--l-fg,#0f172a)" font-weight="600">true, quote did not match</text>
<rect x="556.0" y="380.0" width="131.0" height="28.0" rx="14" class="bad" opacity=".9"/>
<text x="621.5" y="398.5" class="t-tag" text-anchor="middle" fill="#ffffff" font-weight="600">wrong date caught</text>
<rect x="697.0" y="380.0" width="145.0" height="28.0" rx="14" class="bad" opacity=".9"/>
<text x="769.5" y="398.5" class="t-tag" text-anchor="middle" fill="#ffffff" font-weight="600">wrong number caught</text>
<text x="0.0" y="432.0" class="fg2 t-tag" text-anchor="start" >Without the layer, two answers would have carried a wrong detail (8 to 13 cm for 8 to 12 cm; a date off by ten days); two true statements were lost.</text>
</svg>
`,tcga:`<svg xmlns="http://www.w3.org/2000/svg" class="vfig" viewBox="0 0 960 482" width="960" height="482" role="img" aria-label="Agreement with the TCGA clinical record on real pathology reports"><style>.vfig .fg{fill:var(--l-fg,#0f172a)}.vfig .fg2{fill:var(--l-fg-2,#475569)}.vfig .fg3{fill:var(--l-fg-3,#94a3b8)}.vfig .ln{stroke:var(--l-line,#e2e8f0)}.vfig .ln2{stroke:var(--l-line-2,#cbd5e1)}.vfig .ax{stroke:var(--l-fg-3,#94a3b8)}.vfig .bg{fill:var(--l-surface,#ffffff)}.vfig .band{fill:var(--l-accent-bg,rgba(1,180,194,.09))}.vfig .neu{fill:var(--l-line-2,#cbd5e1)}.vfig .med{fill:#0e9aa7}.vfig .gen{fill:#7c5cf0}.vfig .medS{stroke:#0e9aa7}.vfig .genS{stroke:#7c5cf0}.vfig .warm{fill:#e8973a}.vfig .warmS{stroke:#e8973a}.vfig .bad{fill:#e35d6a}.vfig text{font-family:'Inter Variable', Inter, system-ui, sans-serif}.vfig .t-num,.vfig .t-ax{font-variant-numeric:tabular-nums}.vfig .t-title{font-size:19px;font-weight:650;letter-spacing:-.01em}.vfig .t-sub{font-size:13.5px}.vfig .t-lab{font-size:13.5px;font-weight:550}.vfig .t-tag{font-size:11.5px}.vfig .t-num{font-size:12.5px;font-weight:600}.vfig .t-ax{font-size:12px} </style>
<text x="0.0" y="22.0" class="fg t-title" text-anchor="start" >2,102 real pathology reports against the clinical record</text>
<text x="0.0" y="44.0" class="fg2 t-sub" text-anchor="start" >Shipped extractor (Qwen3.5-4B, Chinese, non-medical). 10,883 values read; 151 had no verifiable quote and are flagged. Tick: lower 95 % bound.</text>
<text x="710.0" y="98.0" class="fg2 t-tag" text-anchor="start" >Differences the report itself states</text>
<line x1="190.0" y1="106.0" x2="190.0" y2="406.0" class="ln" stroke-width="1" />
<text x="190.0" y="424.0" class="fg3 t-ax" text-anchor="middle" >0</text>
<line x1="284.0" y1="106.0" x2="284.0" y2="406.0" class="ln" stroke-width="1" />
<text x="284.0" y="424.0" class="fg3 t-ax" text-anchor="middle" >20</text>
<line x1="378.0" y1="106.0" x2="378.0" y2="406.0" class="ln" stroke-width="1" />
<text x="378.0" y="424.0" class="fg3 t-ax" text-anchor="middle" >40</text>
<line x1="472.0" y1="106.0" x2="472.0" y2="406.0" class="ln" stroke-width="1" />
<text x="472.0" y="424.0" class="fg3 t-ax" text-anchor="middle" >60</text>
<line x1="566.0" y1="106.0" x2="566.0" y2="406.0" class="ln" stroke-width="1" />
<text x="566.0" y="424.0" class="fg3 t-ax" text-anchor="middle" >80</text>
<line x1="660.0" y1="106.0" x2="660.0" y2="406.0" class="ln" stroke-width="1" />
<text x="660.0" y="424.0" class="fg3 t-ax" text-anchor="middle" >100</text>
<text x="425.0" y="444.0" class="fg2 t-ax" text-anchor="middle" >Agreement with the record, %</text>
<text x="0.0" y="134.0" class="fg t-lab" text-anchor="start" >Histology</text>
<text x="0.0" y="148.0" class="fg3 t-tag" text-anchor="start" >1,961 of 2,012</text>
<rect x="190.0" y="124.0" width="458.2" height="18.0" rx="6" class="med" opacity=".9"/>
<line x1="644.5" y1="120.0" x2="644.5" y2="146.0" class="ax" stroke-width="2" />
<text x="658.2" y="137.5" class="fg t-num" text-anchor="start" >97.5</text>
<rect x="710.0" y="127.0" width="120.0" height="12.0" rx="6" class="neu" />
<rect x="710.0" y="127.0" width="115.3" height="12.0" rx="6" class="warm" />
<text x="840.0" y="137.5" class="fg t-num" text-anchor="start" >49 of 51</text>
<text x="0.0" y="176.0" class="fg t-lab" text-anchor="start" >pT</text>
<text x="0.0" y="190.0" class="fg3 t-tag" text-anchor="start" >1,244 of 1,280</text>
<rect x="190.0" y="166.0" width="456.8" height="18.0" rx="6" class="med" opacity=".9"/>
<line x1="641.7" y1="162.0" x2="641.7" y2="188.0" class="ax" stroke-width="2" />
<text x="656.8" y="179.5" class="fg t-num" text-anchor="start" >97.2</text>
<rect x="710.0" y="169.0" width="120.0" height="12.0" rx="6" class="neu" />
<rect x="710.0" y="169.0" width="116.7" height="12.0" rx="6" class="warm" />
<text x="840.0" y="179.5" class="fg t-num" text-anchor="start" >35 of 36</text>
<text x="0.0" y="218.0" class="fg t-lab" text-anchor="start" >pN</text>
<text x="0.0" y="232.0" class="fg3 t-tag" text-anchor="start" >556 of 571</text>
<rect x="190.0" y="208.0" width="457.8" height="18.0" rx="6" class="med" opacity=".9"/>
<line x1="639.8" y1="204.0" x2="639.8" y2="230.0" class="ax" stroke-width="2" />
<text x="657.8" y="221.5" class="fg t-num" text-anchor="start" >97.4</text>
<rect x="710.0" y="211.0" width="120.0" height="12.0" rx="6" class="neu" />
<rect x="710.0" y="211.0" width="120.0" height="12.0" rx="6" class="warm" />
<text x="840.0" y="221.5" class="fg t-num" text-anchor="start" >15 of 15</text>
<text x="0.0" y="260.0" class="fg t-lab" text-anchor="start" >Stage group</text>
<text x="0.0" y="274.0" class="fg3 t-tag" text-anchor="start" >70 of 75</text>
<rect x="190.0" y="250.0" width="438.5" height="18.0" rx="6" class="med" opacity=".9"/>
<line x1="590.9" y1="246.0" x2="590.9" y2="272.0" class="ax" stroke-width="2" />
<text x="638.5" y="263.5" class="fg t-num" text-anchor="start" >93.3</text>
<rect x="710.0" y="253.0" width="120.0" height="12.0" rx="6" class="neu" />
<rect x="710.0" y="253.0" width="120.0" height="12.0" rx="6" class="warm" />
<text x="840.0" y="263.5" class="fg t-num" text-anchor="start" >5 of 5</text>
<text x="0.0" y="302.0" class="fg t-lab" text-anchor="start" >ER</text>
<text x="0.0" y="316.0" class="fg3 t-tag" text-anchor="start" >495 of 542</text>
<rect x="190.0" y="292.0" width="429.1" height="18.0" rx="6" class="med" opacity=".9"/>
<line x1="606.9" y1="288.0" x2="606.9" y2="314.0" class="ax" stroke-width="2" />
<text x="629.1" y="305.5" class="fg t-num" text-anchor="start" >91.3</text>
<rect x="710.0" y="295.0" width="120.0" height="12.0" rx="6" class="neu" />
<rect x="710.0" y="295.0" width="117.4" height="12.0" rx="6" class="warm" />
<text x="840.0" y="305.5" class="fg t-num" text-anchor="start" >46 of 47</text>
<text x="0.0" y="344.0" class="fg t-lab" text-anchor="start" >PR</text>
<text x="0.0" y="358.0" class="fg3 t-tag" text-anchor="start" >485 of 538</text>
<rect x="190.0" y="334.0" width="423.5" height="18.0" rx="6" class="med" opacity=".9"/>
<line x1="600.3" y1="330.0" x2="600.3" y2="356.0" class="ax" stroke-width="2" />
<text x="623.5" y="347.5" class="fg t-num" text-anchor="start" >90.1</text>
<rect x="710.0" y="337.0" width="120.0" height="12.0" rx="6" class="neu" />
<rect x="710.0" y="337.0" width="117.7" height="12.0" rx="6" class="warm" />
<text x="840.0" y="347.5" class="fg t-num" text-anchor="start" >52 of 53</text>
<text x="0.0" y="386.0" class="fg t-lab" text-anchor="start" >HER2 (IHC)</text>
<text x="0.0" y="400.0" class="fg3 t-tag" text-anchor="start" >346 of 411</text>
<rect x="190.0" y="376.0" width="395.7" height="18.0" rx="6" class="med" opacity=".9"/>
<line x1="567.4" y1="372.0" x2="567.4" y2="398.0" class="ax" stroke-width="2" />
<text x="595.7" y="389.5" class="fg t-num" text-anchor="start" >84.2</text>
<rect x="710.0" y="379.0" width="120.0" height="12.0" rx="6" class="neu" />
<rect x="710.0" y="379.0" width="116.3" height="12.0" rx="6" class="warm" />
<text x="840.0" y="389.5" class="fg t-num" text-anchor="start" >63 of 65</text>
</svg>
`},T=Object.fromEntries(u.models.map(e=>[e.key,e])),E=e=>T[e].name,D=e=>[(0,d.jsx)(h,{v:T[e].country},`o`),(0,d.jsx)(g,{v:T[e].type},`t`)],O=[`MedQA`,`MedMCQA`,`PubMedQA`,`MMLU-Med`,`MedXpertQA`],k=e=>e.replace(/\$\^\{(\w)\}\$/g,` ($1)`);function A(){return(0,d.jsx)(_,{n:1,caption:r.models.caption,testId:`research-table-models`,head:[`Model`,`Params`,`Developer`,`Origin`,`Type`,`Reads images`,`Earlier report`],rows:u.models.map(e=>[e.name,e.params,e.developer,(0,d.jsx)(h,{v:e.country},`o`),(0,d.jsx)(g,{v:e.type},`t`),e.images?`Yes`:`No`,e.previous?`Yes`:`New`])})}function j(){return(0,d.jsx)(_,{n:3,caption:r.text.cot.caption,testId:`research-text-cot`,head:[`#`,`Model`,`Origin`,`Type`,...O,`Overall`,`Min parsed %`],numeric:[0,4,5,6,7,8,9,10],boldMax:[4,5,6,7,8],rows:u.textCot.map((e,t)=>[String(t+1),E(e.key),...D(e.key),...e.acc,e.overall,e.minParsed])})}function M(){return(0,d.jsx)(_,{n:4,caption:r.text.direct.caption,testId:`research-text-direct`,size:`sm`,head:[`Model`,`Origin`,`Type`,...O,`Overall`,`First-token
overall`,`Parsed %`,`CoT gain`],numeric:[3,4,5,6,7,8,9,10,11],rows:u.textDirect.map(e=>[e.rescored?`${E(e.key)} †`:E(e.key),...D(e.key),...e.acc,e.overall,f(e.overallFt),f(e.minParsed),p(e.cotGain)])})}function N(){let e=[],t=r.text.published.rows;for(let n of u.publishedText){let r=n.published,i=n.ours.map((e,t)=>r[t]==null?null:e-r[t]),a=i.filter(e=>e!=null);e.push({cells:[E(n.key),t[0],...n.ours.map(f),``],sep:!0}),e.push({cells:[``,`${t[1]} (${k(n.src)})`,...r.map(f),``],dim:!0}),e.push({cells:[``,t[2],...i.map(p),p(a.reduce((e,t)=>e+t,0)/a.length)],strong:!0})}return(0,d.jsx)(_,{n:5,caption:r.text.published.caption,note:r.text.published.note,testId:`research-text-published`,head:[`Model`,`Row`,...O,`Mean diff.`],numeric:[2,3,4,5,6,7],rows:e})}function P(){let e=[],t=r.text.q4.rows;for(let n of u.q4){let r=n.q4.reduce((e,t)=>e+t,0)/5,i=e=>p(e.reduce((e,t)=>e+t,0)/5-r);e.push({cells:[E(n.key),t[0],...n.q4.map(f),``],sep:!0,dim:!0}),e.push({cells:[``,t[1],...n.direct.map(f),i(n.direct)]}),e.push({cells:[``,t[2],...n.cot.map(f),i(n.cot)],strong:!0})}return(0,d.jsx)(_,{n:6,caption:r.text.q4.caption,testId:`research-q4`,head:[`Model`,`Run`,...O,`Mean gain`],numeric:[2,3,4,5,6,7],rows:e})}function F(){return(0,d.jsx)(_,{n:10,caption:r.image.all.caption,testId:`research-image-all`,size:`sm`,head:[`Model`,`Origin`,`Type`,`VQA-RAD`,`SLAKE`,`PathVQA`,`PMC-VQA`,`MedXpertQA
MM`,`PMC-VQA
CoT`,`MedXpertQA
MM, CoT`,`OmniMedVQA
strict`,`OmniMedVQA
first-token`],numeric:[3,4,5,6,7,8,9,10,11],rows:u.image.map(e=>{let t=e.overall,n=e.cot;return[E(e.key),...D(e.key),t.vqa_rad,t.slake,t.pathvqa,t.pmc_vqa,t.medxpertqa_mm,n.pmc_vqa,n.medxpertqa_mm,t.omnimedvqa,e.omniFt]})})}function I(){return(0,d.jsx)(_,{n:11,caption:r.image.split.caption,testId:`research-image-split`,head:[`Model`,`Origin`,`Type`,`VQA-RAD
yes/no`,`VQA-RAD
open`,`SLAKE
yes/no`,`SLAKE
open`,`PathVQA
yes/no`,`PathVQA
open`],numeric:[3,4,5,6,7,8],rows:u.image.map(e=>[E(e.key),...D(e.key),...e.split.vqa_rad,...e.split.slake,...e.split.pathvqa])})}function L(){return(0,d.jsx)(_,{n:12,caption:r.image.omni.caption,testId:`research-omni`,size:`sm`,head:[`Model`,`Origin`,`Type`,`Strict`,`First-token`,`Parsed %`,`Errors`,...u.omniTypes.map(e=>e.replace(` `,`
`))],numeric:[3,4,5,6,7,8,9,10,11],rows:u.image.map(e=>[E(e.key),...D(e.key),e.overall.omnimedvqa,e.omniFt,e.omniParsed,m(e.omniErrors),...e.byType])})}function R(){return(0,d.jsx)(_,{n:13,caption:r.image.published.caption,testId:`research-image-published`,size:`sm`,head:[`Model`,`Benchmark`,`This run`,`Our protocol`,`Published`,`Source`,`Diff.`,`Like for like?`],numeric:[2,4,6],wrap:[7],rows:u.publishedImage.map(e=>[E(e.key),e.benchmark,e.ours,e.protocol,e.published,e.src,p(e.ours-e.published),e.like])})}function z(){return(0,d.jsx)(_,{n:14,caption:r.throughput.caption,testId:`research-table-throughput`,maxW:`52rem`,head:[`Model`,`Protocol`,`Load (s)`,`Run (s)`,`Mean generated tokens`],numeric:[2,3,4],rows:u.throughput.map(e=>[E(e.key),e.protocol===`cot`?`step-by-step`:`direct`,m(Math.round(e.load??0)),m(Math.round(e.total??0)),m(Math.round(e.genTokens))])})}function B(){return(0,d.jsx)(_,{n:15,caption:r.grounded.bakeoff.caption,testId:`research-bakeoff`,size:`sm`,head:[`Model`,`Origin`,`Type`,`Reader
word recall`,`Invented
numbers`,`Reader s
(5 scans)`,`Doc. types`,`Fields`,`Fabricated`,`Extractor s
(31 docs)`],numeric:[3,4,5,6,7,8,9],rows:u.bakeoff.map(e=>[E(e.key),...D(e.key),e.readerRecall,e.invented,e.readerS,e.types,e.fields,e.fabricated,e.extractorS])})}function V(){return(0,d.jsx)(_,{n:16,caption:r.grounded.answerability.caption,testId:`research-answerability`,maxW:`52rem`,head:[`Reasoner`,`Origin`,`Type`,`Pass`,`Fabrications`,`Mean latency (s)`],numeric:[3,4,5],rows:u.answerability.map(e=>[E(e.key),...D(e.key),e.pass_,e.fabrications,e.latency])})}function H(){return(0,d.jsx)(_,{n:20,caption:r.grounded.status.caption,testId:`research-status`,maxW:`34rem`,head:[`Evidence in the report`,`Share of the 9,523 reports`],numeric:[1],rows:u.status.rows.map(([e,t])=>[e,t])})}function U(){return(0,d.jsxs)(d.Fragment,{children:[(0,d.jsx)(_,{n:21,caption:r.grounded.ocr.captionEngines,testId:`research-ocr`,maxW:`52rem`,head:[`Engine`,`Number recall %`,`Number precision %`,`s / page (median)`,`Threads per page`],numeric:[1,2,3,4],rows:u.ocr.map(e=>[e.engine,e.recall,e.precision,e.sPage,e.threads])}),(0,d.jsx)(_,{n:22,caption:r.grounded.ocr.captionCheck,testId:`research-ocr-check`,maxW:`60rem`,head:[`Check`,`False alarms`,`Substitutions caught %`,`Insertions caught %`,`Deletions caught %`],numeric:[1,2,3,4],wrap:[0],rows:u.ocrCheck.map(e=>[e.check,e.falseAlarms,e.subs,e.ins,e.dels])})]})}var W=u.experiments??{};function G(){let e=W.ciText??[];if(!e.length)return null;let t=e=>`${f(e[1])} to ${f(e[2])}`;return(0,d.jsx)(_,{n:7,caption:r.text.uncertainty.captionCi,testId:`research-ci`,maxW:`60rem`,head:[`Model`,`Origin`,`Type`,`CoT overall`,`95 % CI`,`Direct overall`,`95 % CI`],numeric:[3,4,5,6],rows:e.map(e=>[E(e.key),...D(e.key),e.cot[0],t(e.cot),e.direct[0],t(e.direct)])})}function K(){let e=W.paired??[];return e.length?(0,d.jsx)(_,{n:8,caption:r.text.uncertainty.captionPaired,testId:`research-paired`,size:`sm`,head:[`Comparison`,`Difference`,`95 % CI`,`Only first right`,`Only second right`,`McNemar p`],numeric:[1,2,3,4,5],wrap:[0],rows:e.map(e=>[e.comparison.replace(` ('matches')`,``),p(e.diff),`${p(e.lo)} to ${p(e.hi)}`,m(e.a_only),m(e.b_only),e.p_mcnemar<.001?`< 0.001`:e.p_mcnemar.toFixed(2)])}):null}function q(){let e=W.oncology;return e?(0,d.jsx)(_,{n:9,caption:r.text.oncology.caption,testId:`research-oncology`,maxW:`60rem`,head:[`Model`,`Origin`,`Type`,`Cancer, CoT`,`95 % CI`,`Other questions, CoT`,`Cancer, direct`],numeric:[3,4,5,6],rows:e.rows.map(e=>[E(e.key),...D(e.key),e.oncology[0],`${f(e.oncology[1])} to ${f(e.oncology[2])}`,e.rest[0],e.direct[0]])}):null}function J(){let e=W.probesScale;if(!e)return null;let t=r.grounded.probes.rows;return(0,d.jsx)(_,{n:17,caption:r.grounded.probes.caption,testId:`research-probes`,maxW:`56rem`,head:[`Probe kind`,`Probes`,`Right answer`,`What a right answer is`],numeric:[1,2],wrap:[3],rows:[[t.ans,m(e.ans.n),m(e.ans.pass),t.ansWhat],[t.trap,m(e.absent_true_trap.n),m(e.absent_true_trap.pass),t.trapWhat],[t.scope,m(e.scope.n),m(e.scope.pass),t.scopeWhat],[t.documented,m(e.absent_documented_after_all),m(e.absent_documented_after_all),t.documentedWhat],[t.hand,m(e.hand_written.n),m(e.hand_written.pass),t.handWhat]]})}function Y(){let e=W.probesScale;return e?(0,d.jsx)(_,{n:18,caption:r.grounded.probes.captionRemoved,testId:`research-removed`,size:`sm`,head:[`Case`,`Statement the reasoner wrote`,`Why removed`,`Review against the document`],wrap:[1,3],rows:e.statements_removed_by_grounding.map(e=>[e.case,e.text,String(e.reason).replace(/_/g,` `),`${e.review}: ${e.note}`])}):null}function X(){let e=W.tcgaScale;if(!e)return null;let t=[`ER`,`PR`,`HER2 (IHC)`,`Histology`,`pT`,`pN`,`Stage group`].filter(t=>e.agreement[t]),n=e.disagreements_with_verified_quote??{};return(0,d.jsx)(_,{n:19,caption:r.grounded.tcga.caption,testId:`research-tcga-scale`,maxW:`60rem`,head:[`Field`,`Agree`,`Compared`,`Agreement %`,`Lower 95 % bound`,`Disagreements the report states`],numeric:[1,2,3,4,5],rows:t.map(t=>[t,m(e.agreement[t].agree),m(e.agreement[t].n),e.agreement[t].pct,e.agreement[t].lower95_pct,n[t]?`${n[t].verified} of ${n[t].of}`:`–`])})}var Z=[[`abstract`,r.abstract.title],[`why`,r.why.title],[`models`,r.models.title],[`benchmarks`,r.data.title],[`protocol`,r.protocol.title],[`text`,r.text.title],[`image`,r.image.title],[`throughput`,r.throughput.title],[`grounded`,r.grounded.title],[`findings`,r.findings.title],[`caveats`,r.caveats.title],[`uses`,r.uses.title],[`sources`,r.sources.title]];function Q(){let e=r.paper,t=u.dataCards.filter(e=>e.kind===`text`),f=u.dataCards.filter(e=>e.kind===`image`),p={...r.data.fields,kind:``};return(0,d.jsxs)(o,{title:`Vaidyx research`,testId:`research`,children:[(0,d.jsx)(l,{eyebrow:r.eyebrow,title:[r.title[0],r.title[1]],lead:r.lead,compact:!0}),(0,d.jsx)(`section`,{className:`l-section pb-24 sm:pb-32`,children:(0,d.jsxs)(`div`,{className:`mx-auto max-w-[1240px] px-5 sm:px-8`,children:[(0,d.jsxs)(a,{className:`l-card p-6 sm:p-9`,testId:`research-paper`,children:[(0,d.jsxs)(`div`,{className:`grid gap-8 lg:grid-cols-[1fr_auto] lg:items-start`,children:[(0,d.jsxs)(`div`,{className:`min-w-0`,children:[(0,d.jsxs)(`span`,{className:`l-eyebrow`,children:[e.kind,` · `,e.date]}),(0,d.jsx)(`h2`,{className:`l-title mt-3 text-[clamp(1.5rem,2.8vw,2.3rem)]`,children:e.title}),(0,d.jsx)(`p`,{className:`r-byline mt-5`,children:e.authors.map((t,n)=>(0,d.jsxs)(`span`,{children:[n>0?`, `:``,(0,d.jsx)(`b`,{children:t}),t===e.corresponding?(0,d.jsx)(`sup`,{"aria-label":`corresponding author`,children:`*`}):null]},t))}),(0,d.jsx)(`p`,{className:`r-byline mt-1`,children:e.affiliation})]}),(0,d.jsxs)(`a`,{href:e.file,className:`l-btn l-btn-dark shrink-0`,download:!0,"data-testid":`research-download`,children:[(0,d.jsx)(s,{className:`size-4`,"aria-hidden":!0}),` `,e.download]})]}),(0,d.jsx)(i,{className:`mt-8 grid grid-cols-2 gap-4 border-t pt-7 sm:grid-cols-4`,itemClassName:`min-w-0`,amount:.3,children:e.facts.map(([e,t])=>(0,d.jsxs)(`div`,{children:[(0,d.jsx)(`div`,{className:`r-fact`,children:e}),(0,d.jsx)(`div`,{className:`l-mini l-muted mt-1.5 uppercase tracking-[0.12em]`,children:t})]},t))})]}),(0,d.jsx)(a,{y:10,className:`mt-6`,children:(0,d.jsxs)(`nav`,{"aria-label":r.contents,className:`r-toc l-box px-6 py-5 sm:px-8`,"data-testid":`research-contents`,children:[(0,d.jsx)(`span`,{className:`l-eyebrow`,children:r.contents}),(0,d.jsx)(`ol`,{className:`mt-4 grid gap-x-8 gap-y-2 text-[14px] leading-snug sm:grid-cols-2 lg:grid-cols-4`,children:Z.map(([e,t],n)=>(0,d.jsxs)(`li`,{className:`flex gap-2`,children:[(0,d.jsx)(`span`,{className:`l-faint w-5 shrink-0 tabular-nums`,children:n+1}),(0,d.jsx)(`a`,{href:`#${e}`,children:t})]},e))})]})}),(0,d.jsx)(`div`,{className:`mt-14 sm:mt-20`,children:(0,d.jsxs)(`article`,{className:`min-w-0 space-y-2`,children:[(0,d.jsx)(v,{id:`abstract`,n:1,title:r.abstract.title,children:r.abstract.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24)))}),(0,d.jsx)(v,{id:`why`,n:2,title:r.why.title,children:r.why.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24)))}),(0,d.jsxs)(v,{id:`models`,n:3,title:r.models.title,children:[r.models.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24))),(0,d.jsx)(A,{})]}),(0,d.jsxs)(v,{id:`benchmarks`,n:4,title:r.data.title,children:[r.data.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24))),(0,d.jsxs)(`div`,{"data-testid":`research-datacards`,children:[(0,d.jsx)(a,{y:10,children:(0,d.jsxs)(`p`,{className:`r-cap mb-4`,children:[(0,d.jsx)(`b`,{children:`Table 2.`}),` `,r.data.caption]})}),(0,d.jsx)(i,{className:`grid gap-4 sm:grid-cols-2 lg:grid-cols-3`,amount:.1,children:t.map(({key:e,...t})=>(0,d.jsx)(S,{...t,labels:{...p,kind:r.data.textLabel}},e))}),(0,d.jsx)(i,{className:`mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3`,amount:.1,children:f.map(({key:e,...t})=>(0,d.jsx)(S,{...t,labels:{...p,kind:r.data.imageLabel}},e))})]})]}),(0,d.jsx)(v,{id:`protocol`,n:5,title:r.protocol.title,children:(0,d.jsx)(a,{y:10,children:(0,d.jsx)(x,{items:r.protocol.items})})}),(0,d.jsxs)(v,{id:`text`,n:6,title:r.text.title,children:[(0,d.jsxs)(y,{n:`6.1`,title:r.text.cot.title,children:[(0,d.jsx)(b,{children:r.text.cot.text}),(0,d.jsx)(C,{n:1,svg:w.ranking,caption:r.figures.ranking,testId:`fig-ranking`}),(0,d.jsx)(j,{})]}),(0,d.jsxs)(y,{n:`6.2`,title:r.text.direct.title,children:[(0,d.jsx)(b,{children:r.text.direct.text}),(0,d.jsx)(C,{n:2,svg:w.reasoning,caption:r.figures.reasoning,testId:`fig-reasoning`}),(0,d.jsx)(M,{})]}),(0,d.jsxs)(y,{n:`6.3`,title:r.text.published.title,children:[(0,d.jsx)(b,{children:r.text.published.text}),(0,d.jsx)(C,{n:3,svg:w.published,caption:r.figures.published,testId:`fig-published`}),(0,d.jsx)(N,{})]}),(0,d.jsxs)(y,{n:`6.4`,title:r.text.q4.title,children:[(0,d.jsx)(b,{children:r.text.q4.text}),(0,d.jsx)(C,{n:4,svg:w.q4,caption:r.figures.q4,testId:`fig-q4`}),(0,d.jsx)(P,{})]}),(0,d.jsxs)(y,{n:`6.5`,title:r.text.uncertainty.title,children:[(0,d.jsx)(b,{children:r.text.uncertainty.text}),(0,d.jsx)(G,{}),(0,d.jsx)(K,{})]}),(0,d.jsxs)(y,{n:`6.6`,title:r.text.oncology.title,children:[(0,d.jsx)(b,{children:r.text.oncology.text}),(0,d.jsx)(C,{n:5,svg:w.oncology,caption:r.figures.oncology,testId:`fig-oncology`}),(0,d.jsx)(q,{})]})]}),(0,d.jsxs)(v,{id:`image`,n:7,title:r.image.title,children:[(0,d.jsxs)(y,{n:`7.1`,title:r.image.all.title,children:[(0,d.jsx)(b,{children:r.image.all.text}),(0,d.jsx)(C,{n:6,svg:w.images,caption:r.figures.images,testId:`fig-images`}),(0,d.jsx)(F,{})]}),(0,d.jsxs)(y,{n:`7.2`,title:r.image.split.title,children:[(0,d.jsx)(b,{children:r.image.split.text}),(0,d.jsx)(I,{})]}),(0,d.jsxs)(y,{n:`7.3`,title:r.image.omni.title,children:[(0,d.jsx)(b,{children:r.image.omni.text}),(0,d.jsx)(L,{})]}),(0,d.jsxs)(y,{n:`7.4`,title:r.image.published.title,children:[(0,d.jsx)(b,{children:r.image.published.text}),(0,d.jsx)(R,{})]})]}),(0,d.jsxs)(v,{id:`throughput`,n:8,title:r.throughput.title,children:[(0,d.jsx)(b,{children:r.throughput.text}),(0,d.jsx)(z,{})]}),(0,d.jsxs)(v,{id:`grounded`,n:9,title:r.grounded.title,children:[(0,d.jsx)(b,{children:r.grounded.intro}),(0,d.jsxs)(y,{n:`9.1`,title:r.grounded.bakeoff.title,children:[(0,d.jsx)(b,{children:r.grounded.bakeoff.text}),(0,d.jsx)(B,{})]}),(0,d.jsxs)(y,{n:`9.2`,title:r.grounded.answerability.title,children:[(0,d.jsx)(b,{children:r.grounded.answerability.text}),(0,d.jsx)(V,{})]}),(0,d.jsxs)(y,{n:`9.3`,title:r.grounded.probes.title,children:[r.grounded.probes.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24))),(0,d.jsx)(J,{}),(0,d.jsx)(C,{n:7,svg:w.grounding,caption:r.figures.grounding,testId:`fig-grounding`}),(0,d.jsx)(Y,{})]}),(0,d.jsxs)(y,{n:`9.4`,title:r.grounded.tcga.title,children:[r.grounded.tcga.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24))),(0,d.jsx)(C,{n:8,svg:w.tcga,caption:r.figures.tcga,testId:`fig-tcga`}),(0,d.jsx)(X,{})]}),(0,d.jsxs)(y,{n:`9.5`,title:r.grounded.status.title,children:[(0,d.jsx)(b,{children:r.grounded.status.text}),(0,d.jsx)(H,{})]}),(0,d.jsx)(y,{n:`9.6`,title:r.grounded.summary.title,children:(0,d.jsx)(b,{children:r.grounded.summary.text})}),(0,d.jsxs)(y,{n:`9.7`,title:r.grounded.ocr.title,children:[r.grounded.ocr.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24))),(0,d.jsx)(U,{})]}),(0,d.jsx)(y,{n:`9.8`,title:r.grounded.speed.title,children:(0,d.jsx)(b,{children:r.grounded.speed.text})})]}),(0,d.jsxs)(v,{id:`findings`,n:10,title:r.findings.title,children:[(0,d.jsx)(a,{y:10,children:(0,d.jsx)(x,{items:r.findings.items,as:`ul`})}),(0,d.jsx)(C,{n:9,svg:w.size,caption:r.figures.size,testId:`fig-size`})]}),(0,d.jsx)(v,{id:`caveats`,n:11,title:r.caveats.title,children:(0,d.jsx)(a,{y:10,children:(0,d.jsx)(x,{items:r.caveats.items,as:`ul`})})}),(0,d.jsx)(v,{id:`uses`,n:12,title:r.uses.title,children:r.uses.text.map(e=>(0,d.jsx)(b,{children:e},e.slice(0,24)))}),(0,d.jsxs)(v,{id:`sources`,n:13,title:r.sources.title,children:[(0,d.jsx)(b,{className:`r-note`,children:r.sources.note}),(0,d.jsx)(a,{y:10,children:(0,d.jsx)(`ul`,{className:`grid gap-2 sm:grid-cols-2 lg:grid-cols-3`,children:r.sources.items.map(e=>(0,d.jsx)(`li`,{children:(0,d.jsxs)(`a`,{href:e.href,target:`_blank`,rel:`noreferrer`,className:`l-source text-[14px]`,children:[e.label,` `,(0,d.jsx)(c,{className:`size-3.5`,"aria-hidden":!0})]})},e.href))})})]})]})})]})}),(0,d.jsx)(n,{})]})}export{Q as default};