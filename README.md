<div align="center" markdown>
<img src="https://user-images.githubusercontent.com/48245050/182403218-5ab9905c-5b79-442e-b8e1-c1a1a274c81d.png"/>

# Import images from cloud storage

<p align="center">
  <a href="#Overview">Overview</a> •
  <a href="#How-To-Use">How To Use</a>
</p>


[![](https://img.shields.io/badge/supervisely-ecosystem-brightgreen)](https://ecosystem.supervisely.com/apps/supervisely-ecosystem/import-images-from-cloud-storage)
[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervisely.com/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/import-images-from-cloud-storage)
[![views](https://app.supervisely.com/img/badges/views/supervisely-ecosystem/import-images-from-cloud-storage.png)](https://supervisely.com)
[![runs](https://app.supervisely.com/img/badges/runs/supervisely-ecosystem/import-images-from-cloud-storage.png)](https://supervisely.com)

</div>

# Overview

This apps allows to import images from most popular cloud storage providers to Supervisely Private instance.

List of providers:
- Amazon s3
- Google Cloud Storage (CS)
- Microsoft Azure
- and others with s3 compatible interfaces

App supports two types of import:
1. copy images from cloud to Supervisely Storage
2. add images by link

⚠️ Notice: for any of these import types app downloads image to its temp directory, processes it and extracts some
technical information like timestamp-frame index mapping, number of streams, resolution and so on. Once the video is
processed, it will be removed from temp directory. This is the one time procedure.

# How To Use

0. Ask your instance administrator to add cloud credentials to instance settings. It can be done both in .env
   configuration files or in Admin UI dashboard. Learn more in docs: [link1](https://docs.supervisely.com/enterprise-edition/installation/post-installation#configure-your-instance), 
   [link2](https://docs.supervisely.com/enterprise-edition/advanced-tuning/s3#links-plugin-cloud-providers-support).
   In case of any questions or issues, please contact tech support.
1. Add app to your team from Ecosystem
2. Run app from `Team Apps` Page
3. Connect to cloud bucket, preview and select files and directories, import selected files to some project/dataset.
   You can perform these actions as many times as needed
3. Once you are ready with the app, you should close app manually


Watch short video for more details:

<a data-key="sly-embeded-video-link" href="https://youtu.be/LJRA84FXHl4" data-video-code="LJRA84FXHl4">
    <img src="https://i.imgur.com/x4aSTNH.png" alt="SLY_EMBEDED_VIDEO_LINK"  style="max-width:500px;">
</a>

# Screenshot

<img src="https://i.imgur.com/qnmDX5w.png"/>
