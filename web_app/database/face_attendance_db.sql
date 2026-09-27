-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Jun 16, 2026 at 09:00 PM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `face_attendance_db`
--

-- --------------------------------------------------------

--
-- Table structure for table `attendance`
--

CREATE TABLE `attendance` (
  `attendance_id` int(11) NOT NULL,
  `session_id` int(11) NOT NULL,
  `student_id` int(11) NOT NULL,
  `status` enum('present','absent','manual_override') NOT NULL DEFAULT 'present',
  `recognition_time` datetime NOT NULL DEFAULT current_timestamp(),
  `confidence` float DEFAULT NULL,
  `override_by` int(11) DEFAULT NULL,
  `override_note` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `course`
--

CREATE TABLE `course` (
  `course_id` int(11) NOT NULL,
  `course_code` varchar(20) NOT NULL,
  `course_name` varchar(150) NOT NULL,
  `credit_hours` tinyint(3) UNSIGNED NOT NULL DEFAULT 3,
  `created_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `course`
--

INSERT INTO `course` (`course_id`, `course_code`, `course_name`, `credit_hours`, `created_at`) VALUES
(1, '2211261', 'Database Systems', 3, '2026-05-13 09:16:43'),
(2, '2211263', 'Oracle Database', 3, '2026-05-13 09:16:43'),
(3, '2211211', 'Data Structures', 3, '2026-05-13 09:16:43'),
(4, '2211121', 'Object-Oriented Programming', 3, '2026-05-13 09:16:43');

-- --------------------------------------------------------

--
-- Table structure for table `excuse_request`
--

CREATE TABLE `excuse_request` (
  `excuse_id` int(11) NOT NULL,
  `student_id` int(11) NOT NULL,
  `section_id` int(11) NOT NULL,
  `session_id` int(11) DEFAULT NULL,
  `excuse_date` date NOT NULL,
  `reason` text NOT NULL,
  `file_path` varchar(255) DEFAULT NULL,
  `status` enum('pending','approved','rejected') DEFAULT 'pending',
  `instructor_note` text DEFAULT NULL,
  `submitted_at` datetime DEFAULT current_timestamp(),
  `reviewed_at` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `section`
--

CREATE TABLE `section` (
  `section_id` int(11) NOT NULL,
  `course_id` int(11) NOT NULL,
  `lecturer_id` int(11) NOT NULL,
  `room_id` varchar(30) DEFAULT NULL,
  `semester` varchar(20) NOT NULL,
  `day_of_week` set('Sun','Mon','Tue','Wed','Thu') DEFAULT NULL,
  `start_time` time DEFAULT NULL,
  `end_time` time DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `section`
--

INSERT INTO `section` (`section_id`, `course_id`, `lecturer_id`, `room_id`, `semester`, `day_of_week`, `start_time`, `end_time`, `created_at`) VALUES
(1, 1, 2, 'Smart-1', 'Spring 2026', 'Sun,Mon,Tue,Wed,Thu', '00:00:00', '23:59:00', '2026-05-14 16:22:50'),
(2, 2, 2, 'Smart-2', 'Spring 2026', 'Mon,Wed', '09:30:00', '11:00:00', '2026-05-14 16:22:50'),
(3, 3, 3, 'Smart-3', 'Spring 2026', 'Sun,Tue,Thu', '11:00:00', '12:00:00', '2026-05-14 16:22:50'),
(4, 4, 3, 'Smart-4', 'Spring 2026', 'Mon,Wed', '11:00:00', '12:30:00', '2026-05-14 16:22:50'),
(5, 1, 3, 'Smart-2', 'Spring 2026', 'Sun,Tue,Thu', '09:00:00', '10:00:00', '2026-05-28 19:42:21'),
(6, 3, 2, 'Smart-3', 'Spring 2026', 'Sun,Tue,Thu', '13:00:00', '14:00:00', '2026-05-28 19:46:21'),
(8, 2, 2, 'Smart-2', 'Spring 2026', 'Sun,Tue,Thu', '12:00:00', '13:00:00', '2026-06-16 18:26:15');

-- --------------------------------------------------------

--
-- Table structure for table `section_students`
--

CREATE TABLE `section_students` (
  `enrollment_id` int(11) NOT NULL,
  `student_id` int(11) NOT NULL,
  `section_id` int(11) NOT NULL,
  `enrolled_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `section_students`
--

INSERT INTO `section_students` (`enrollment_id`, `student_id`, `section_id`, `enrolled_at`) VALUES
(11, 6, 3, '2026-05-31 00:38:49'),
(12, 6, 4, '2026-05-31 00:38:49'),
(13, 7, 6, '2026-05-31 00:38:49'),
(14, 7, 4, '2026-05-31 00:38:49'),
(15, 8, 5, '2026-05-31 00:38:49'),
(16, 8, 2, '2026-05-31 00:38:49'),
(17, 9, 1, '2026-05-31 00:38:49'),
(18, 9, 6, '2026-05-31 00:38:49'),
(19, 10, 3, '2026-05-31 00:38:49'),
(20, 10, 4, '2026-05-31 00:38:49'),
(21, 11, 5, '2026-05-31 00:38:49'),
(22, 11, 2, '2026-05-31 00:38:49'),
(23, 12, 4, '2026-05-31 00:38:49'),
(24, 12, 1, '2026-05-31 00:38:49'),
(25, 13, 3, '2026-05-31 00:38:49'),
(26, 13, 4, '2026-05-31 00:38:49'),
(27, 14, 2, '2026-05-31 00:38:49'),
(28, 14, 5, '2026-05-31 00:38:49'),
(29, 15, 4, '2026-05-31 00:38:49'),
(30, 15, 1, '2026-05-31 00:38:49'),
(31, 16, 3, '2026-05-31 00:38:49'),
(32, 16, 4, '2026-05-31 00:38:49'),
(33, 17, 5, '2026-05-31 00:38:49'),
(34, 17, 2, '2026-05-31 00:38:49'),
(35, 18, 1, '2026-05-31 00:38:49'),
(36, 18, 6, '2026-05-31 00:38:49'),
(37, 19, 6, '2026-05-31 00:38:49'),
(38, 19, 4, '2026-05-31 00:38:49'),
(39, 20, 3, '2026-05-31 00:38:49'),
(40, 20, 4, '2026-05-31 00:38:49'),
(41, 21, 3, '2026-05-31 00:38:49'),
(42, 21, 4, '2026-05-31 00:38:49'),
(43, 22, 2, '2026-05-31 00:38:49'),
(44, 22, 5, '2026-05-31 00:38:49'),
(45, 23, 1, '2026-05-31 00:38:49'),
(46, 23, 6, '2026-05-31 00:38:49'),
(47, 24, 2, '2026-05-31 00:38:49'),
(48, 24, 5, '2026-05-31 00:38:49'),
(49, 25, 2, '2026-05-31 00:38:49'),
(50, 25, 5, '2026-05-31 00:38:49'),
(51, 26, 1, '2026-05-31 00:38:49'),
(52, 26, 6, '2026-05-31 00:38:49'),
(53, 27, 2, '2026-05-31 00:38:49'),
(54, 27, 5, '2026-05-31 00:38:49'),
(55, 28, 1, '2026-05-31 00:38:49'),
(56, 28, 6, '2026-05-31 00:38:49'),
(57, 29, 5, '2026-05-31 00:38:49'),
(58, 29, 2, '2026-05-31 00:38:49'),
(59, 30, 5, '2026-05-31 00:38:49'),
(60, 30, 2, '2026-05-31 00:38:49'),
(61, 31, 4, '2026-05-31 00:38:49'),
(62, 31, 1, '2026-05-31 00:38:49'),
(74, 6, 1, '2026-05-31 00:43:11'),
(75, 7, 1, '2026-05-31 00:43:11'),
(76, 8, 1, '2026-05-31 00:43:11'),
(77, 13, 1, '2026-05-31 00:43:11'),
(78, 21, 1, '2026-05-31 00:43:11'),
(79, 25, 1, '2026-05-31 00:43:11'),
(80, 20, 8, '2026-06-16 21:59:43'),
(81, 6, 8, '2026-06-16 21:59:43'),
(82, 16, 8, '2026-06-16 21:59:43'),
(83, 21, 8, '2026-06-16 21:59:43'),
(84, 25, 8, '2026-06-16 21:59:43'),
(85, 24, 8, '2026-06-16 21:59:43'),
(86, 14, 8, '2026-06-16 21:59:43'),
(87, 8, 8, '2026-06-16 21:59:43'),
(88, 28, 8, '2026-06-16 21:59:43'),
(89, 30, 8, '2026-06-16 21:59:43'),
(90, 29, 8, '2026-06-16 21:59:43'),
(91, 18, 8, '2026-06-16 21:59:43'),
(92, 9, 8, '2026-06-16 21:59:43'),
(93, 19, 8, '2026-06-16 21:59:43'),
(94, 10, 8, '2026-06-16 21:59:43'),
(95, 12, 8, '2026-06-16 21:59:43'),
(96, 7, 8, '2026-06-16 21:59:43');

-- --------------------------------------------------------

--
-- Table structure for table `session`
--

CREATE TABLE `session` (
  `session_id` int(11) NOT NULL,
  `section_id` int(11) NOT NULL,
  `session_date` date NOT NULL,
  `start_time` time NOT NULL,
  `end_time` time NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 0,
  `started_by` int(11) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `student`
--

CREATE TABLE `student` (
  `student_id` int(11) NOT NULL,
  `university_id` varchar(20) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `email` varchar(100) DEFAULT NULL,
  `department` varchar(100) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `face_image` varchar(255) DEFAULT NULL,
  `face_label` varchar(100) DEFAULT NULL,
  `face_registered` tinyint(1) NOT NULL DEFAULT 0
) ;

--
-- Dumping data for table `student`
--

INSERT INTO `student` (`student_id`, `university_id`, `full_name`, `email`, `department`, `is_active`, `created_at`, `updated_at`, `face_image`, `face_label`, `face_registered`) VALUES
(6, '120222211047', 'Abdallah Nader Salem Abuharb', '120222211047@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'abdallah_abuharb', 1),
(7, '420252211517', 'Adam Raed Atef Dalaeen', '420252211517@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'adam_raed', 1),
(8, '120222221073', 'Aya Naser Mahmoud Shamaileh', '120222221073@mutah.edu.jo', 'Computer Information Systems', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'aya_naser', 1),
(9, '120242222063', 'Ayham Ibrahem Abdalazeez Majali', '120242222063@mutah.edu.jo', 'Data Science and Artificial Intelligence', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'ayham_ibrahem', 1),
(10, '120252211058', 'Albarraa Khaled Lafi Bathi', '120252211058@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'barraa_khaled', 1),
(11, '120232221053', 'Fatima Naser Mahmoud Shamaileh', '120232221053@mutah.edu.jo', 'Computer Information Systems', 1, '2026-05-31 00:23:24', '2026-05-31 00:32:22', NULL, 'fatima_naser', 1),
(12, '420222231508', 'Ghaida Mohammad Mahmoud Faraieh', '420222231508@mutah.edu.jo', 'Software Engineering', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'ghaida_mohammed', 1),
(13, '120242211006', 'Hamza Mustafa Saleem Abussaab', '120242211006@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'hamza_buassab', 1),
(14, '120222212098', 'Jana Raed Atef Dalaeen', '120222212098@mutah.edu.jo', 'Information Security and Digital Forensics', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'jana_raed', 1),
(15, '120222231048', 'Leen Moeen MohammadAli Madadha', '120222231048@mutah.edu.jo', 'Software Engineering', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'leen_moeen', 1),
(16, '120222211099', 'Mohammad Ryaad Rashed Maiah', '120222211099@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'mohamad_ryaad', 1),
(17, '120242221070', 'Mohammad Yousef Faiq Rahaifeh', '120242221070@mutah.edu.jo', 'Computer Information Systems', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'mohammed_yousef', 1),
(18, '120242222007', 'Mustafa Rabah Abdalmuty Dalaeen', '120242222007@mutah.edu.jo', 'Data Science and Artificial Intelligence', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'mustafa_rabah', 1),
(19, '120252211016', 'Osama Belal Shaker Shehadeh', '120252211016@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'osama_belal', 1),
(20, '120222211032', 'Rahaf Sofian Sabri Alazzah', '120222211032@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-06-16 18:13:50', NULL, 'rahaf_sofian', 1),
(21, '120222211109', 'Rama Issam Kayed Sawadha', '120222211109@mutah.edu.jo', 'Computer Science', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'rama_issam', 1),
(22, '120222212046', 'Raneem Abdullah Khaled Thnebat', '120222212046@mutah.edu.jo', 'Information Security and Digital Forensics', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'raneem_abdallah', 1),
(23, '120222222025', 'Saja Ramzi Mahmoud Salameh', '120222222025@mutah.edu.jo', 'Data Science and Artificial Intelligence', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'saja_salameh', 1),
(24, '120222212086', 'Saja Zaid Mohammad Bashabsheh', '120222212086@mutah.edu.jo', 'Information Security and Digital Forensics', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'saja_zaid', 1),
(25, '120222212054', 'Sara Ameen Abdalhafez Maqbeh', '120222212054@mutah.edu.jo', 'Information Security and Digital Forensics', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'sara_amin', 1),
(26, '120222222092', 'Sewar Yahia Jumah Sioof', '120222222092@mutah.edu.jo', 'Data Science and Artificial Intelligence', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'sewar_yahia', 1),
(27, '120252212135', 'Sora Bassam Abdalghany Hjouj', '120252212135@mutah.edu.jo', 'Information Security and Digital Forensics', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'sora_basam', 1),
(28, '120222222008', 'Tabark Ahmad Saleem Bdeerat', '120222222008@mutah.edu.jo', 'Data Science and Artificial Intelligence', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'tabark_ahmad', 1),
(29, '120232221078', 'Waleed Fadi Nazmi Qasem', '120232221078@mutah.edu.jo', 'Computer Information Systems', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'waleed_fadi', 1),
(30, '120232221015', 'Yaseen Yahia Salem Basiony', '120232221015@mutah.edu.jo', 'Computer Information Systems', 1, '2026-05-31 00:23:24', '2026-05-31 00:23:24', NULL, 'yaseen_yahia', 1),
(31, '120222231083', 'Yousef Jehad Musllem Rawahneh', '120222231083@mutah.edu.jo', 'Software Engineering', 1, '2026-05-31 00:23:24', '2026-05-31 00:32:22', NULL, 'yousef_jehad', 1);

-- --------------------------------------------------------

--
-- Table structure for table `users`
--

CREATE TABLE `users` (
  `user_id` int(11) NOT NULL,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `full_name` varchar(100) NOT NULL,
  `email` varchar(100) NOT NULL,
  `role` enum('admin','instructor','student') NOT NULL DEFAULT 'instructor',
  `student_id` int(11) DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `users`
--

INSERT INTO `users` (`user_id`, `username`, `password_hash`, `full_name`, `email`, `role`, `student_id`, `is_active`, `created_at`) VALUES
(1, 'admin', 'scrypt:32768:8:1$7L9EwM8Nna3Dsp8M$2abb72eaafe5c1a078d82a50357875d46033adb3bc30803cfdd4891fea3e6aa11057b089d25063bd6059875ccabf514f01d35cafae4a28b55ea1f44442e71dd6', 'System Administrator', 'admin@mutah.edu.jo', 'admin', NULL, 1, '2026-05-14 16:19:08'),
(2, 'dr_anas', 'scrypt:32768:8:1$WiEtUCH8usjj7Rvx$24a5ee60dabb06df7f65240164ccb21ba5dcc01ed62fdbe832e222757d76c7519392417b483e999433082548f4c07fe7b662ba5bbcad91dee46d43fdb89a7416', 'Dr. Anas Al-Kasasbeh', 'anas.kasasbeh@mutah.edu.jo', 'instructor', NULL, 1, '2026-05-14 16:19:08'),
(3, 'dr_sara', 'scrypt:32768:8:1$LOPhfRKFXCo4klmd$0acb41f57fcebfe77271c1da9983223fc68069364e10713df28b3bc3bbab81e84675299339c38cb413d48a2716d68208deeaa935e3686f459018710f13991ae1', 'Dr. Sara Mahmoud', 'sara.mahmoud@mutah.edu.jo', 'instructor', NULL, 1, '2026-05-14 16:19:08'),
(5, '120222211047', 'scrypt:32768:8:1$KQBbBDmX6Fw0SdVa$865ea67712b0c9498d472ea6e2a6b6c7fc8323954d5e8cbcb8f7899e9b24e43a6d6ad0115fe2ccc96c9a6f3b095ef7131dd1a1cad56a1ff7b936768b4bb4945d', 'Abdallah Nader Salem Abuharb', '120222211047@mutah.edu.jo', 'student', 6, 1, '2026-06-05 14:26:37'),
(6, '420252211517', 'scrypt:32768:8:1$V9TtOFzjCjPtJdom$9732e0fe2911ff74c4ad52bac90ed005040374e4048c0d52a805bbb153e369fa0d958da26e65d4ab6a080182aaf356ea3050b5ec08cab295a36ea8530fb79650', 'Adam Raed Atef Dalaeen', '420252211517@mutah.edu.jo', 'student', 7, 1, '2026-06-05 14:26:37'),
(7, '120222221073', 'scrypt:32768:8:1$WDiDfM3G95cxJHuV$8506574cb09caab3b5af8b0b4fa5a591f2568248220f45588516277fe0eec39648a66a986c8b36a053701feae59f9a1dadd806c17d00f842c34f977a203e0b65', 'Aya Naser Mahmoud Shamaileh', '120222221073@mutah.edu.jo', 'student', 8, 1, '2026-06-05 14:26:37'),
(8, '120242222063', 'scrypt:32768:8:1$ZMg1yuwUj9hDB7Ch$e3b4946f08e5816199b0f4062e08fba7f9e116a993276d3b047811aab6ce42c09c826dbc235353ce253940f79f985e15e0ebcfdca89fa8a5cb7a4c4dbfaec767', 'Ayham Ibrahem Abdalazeez Majali', '120242222063@mutah.edu.jo', 'student', 9, 1, '2026-06-05 14:26:37'),
(9, '120252211058', 'scrypt:32768:8:1$k2FSFrBZeEd5Ljxa$5af0c9e791170ae86f03e870048967a67ec908e803f0d49e6e0fa8ca4fe49829ce695138307d3f230d914d8053e464492023dbe68484e630684d1b64accd3f8d', 'Albarraa Khaled Lafi Bathi', '120252211058@mutah.edu.jo', 'student', 10, 1, '2026-06-05 14:26:37'),
(10, '120232221053', 'scrypt:32768:8:1$z8wjA0H6cQXm7SHf$890cc4cdef8bddbd9247314779b20f67bccd3cfb239ea3e69339ec9909ec85edd8d94123fc0c97e05aece3d6c9bac2aafc05ab62aba1f1edc3f5fbb45a2e06fb', 'Fatima Naser Mahmoud Shamaileh', '120232221053@mutah.edu.jo', 'student', 11, 1, '2026-06-05 14:26:37'),
(11, '420222231508', 'scrypt:32768:8:1$35wV0SbrdVsUeQIu$bd0b4f7773f0aa55a3835873bb85ac5ccea8202757b05ba5963dcca7110e8ad7c4ccf8280222338fe1508289b364b9932747809601d7299e335807972bade191', 'Ghaida Mohammad Mahmoud Faraieh', '420222231508@mutah.edu.jo', 'student', 12, 1, '2026-06-05 14:26:37'),
(12, '120242211006', 'scrypt:32768:8:1$8YPKVSCMppStoH05$288df47f1d78a85f1639ac0d308e67d2d02cbfe1ae444172c2c59688d62f428bbefee5863fed2ec361bb1b0ada8c53b265c6b00158853644f040d0570632c579', 'Hamza Mustafa Saleem Abussaab', '120242211006@mutah.edu.jo', 'student', 13, 1, '2026-06-05 14:26:37'),
(13, '120222212098', 'scrypt:32768:8:1$qIjiaFHmDFVcfKBG$4047bfffbeda4b36fbab06613d667b7298c55292bed82db61b57f2b8a4e43d48e6eed6dcb4e75fef28a64db4f4fbe4f28cebf0b5434cc03a97cad3c31a88f6b1', 'Jana Raed Atef Dalaeen', '120222212098@mutah.edu.jo', 'student', 14, 1, '2026-06-05 14:26:37'),
(14, '120222231048', 'scrypt:32768:8:1$z0jNsZW6moMfLanZ$9f5e2a1919675050206f87b4bc52e4b39fcd394f6e92929a6cbc4fd4a3b035ecc11f532d68e6af5d80e5d5fac38002b8f52b3ef0bb1cde4f57fb8de597b1b5e1', 'Leen Moeen MohammadAli Madadha', '120222231048@mutah.edu.jo', 'student', 15, 1, '2026-06-05 14:26:37'),
(15, '120222211099', 'scrypt:32768:8:1$AzekHufaDaldJfbz$7e59d23b89bee704db8563e18fbad4f0cd62ac9ec960b0a60d851ca3863f3f0a9e022cb1fc4cec50dac56fdc197da771384b879bce374d0f4135f2d7f6a81ca0', 'Mohammad Ryaad Rashed Maiah', '120222211099@mutah.edu.jo', 'student', 16, 1, '2026-06-05 14:26:37'),
(16, '120242221070', 'scrypt:32768:8:1$OB2BIFHvJc487tmS$b3f572997891e0aed39c7e04e4433c0aff85c818da241ce7e7e42c52d4b491f6b32b16a0550214680460730c1770a15f6cc9816a287affccf7c333fa421777fb', 'Mohammad Yousef Faiq Rahaifeh', '120242221070@mutah.edu.jo', 'student', 17, 1, '2026-06-05 14:26:37'),
(17, '120242222007', 'scrypt:32768:8:1$3PNApvxegZgi4f6t$5140c809eca20961ec2d1a58269d74e2c52939ac5b4f47f22f3829e036bd6b55e070297ea1e21af7288b8e227932b656392d14edf7f03b775e80483215ee7d08', 'Mustafa Rabah Abdalmuty Dalaeen', '120242222007@mutah.edu.jo', 'student', 18, 1, '2026-06-05 14:26:37'),
(18, '120252211016', 'scrypt:32768:8:1$p19br9xMwcUmuQdV$e98dc409bb8134c49a112bf8f0ab9351b693466eb3819989e98af87d0e16914611a386103654925cf918a4a8f114f61633ba3582473de20fbbbfd6a0e683b145', 'Osama Belal Shaker Shehadeh', '120252211016@mutah.edu.jo', 'student', 19, 1, '2026-06-05 14:26:37'),
(19, '120222211032', 'scrypt:32768:8:1$rd70eiMlw331q0h8$93e75a9145b5e9598c3f69f0dfa5419f2f5c2bdc4b463444165e3f8d253770e29491f2d52d57fca1798f0afb160d8fa8da1f28da90f360d5da022d73b20da701', 'Rahaf Sofian Sabri Azzah', '120222211032@mutah.edu.jo', 'student', 20, 1, '2026-06-05 14:26:37'),
(20, '120222211109', 'scrypt:32768:8:1$S855d36EXLzlL3Bx$2d2d089ab9ee0fe3bd57030cd0330f0bd51e92028da7f3ee49d70a6ec8a0e72027e9245641c8b9a28d4aab5b5a682dcee722a32b6b15d0185a43d0d21b5ccb30', 'Rama Issam Kayed Sawadha', '120222211109@mutah.edu.jo', 'student', 21, 1, '2026-06-05 14:26:37'),
(21, '120222212046', 'scrypt:32768:8:1$EicBrfCCmG0KFqLX$88342867bd5d3f8a54344fb6f50c4b7c6d3e9f31cfaeae83e3cf157a5cb4f9776c4f8399b5a5f52f3318c6924c1cbde4f84bd18ee3ec11e232860ef444fe3919', 'Raneem Abdullah Khaled Thnebat', '120222212046@mutah.edu.jo', 'student', 22, 1, '2026-06-05 14:26:37'),
(22, '120222222025', 'scrypt:32768:8:1$sCLAsXhOIRHtOubJ$410eb16337c07fca0ef75656a9c4d7572e44274eeaad4721b32292764d8d5c3ac0752b9b3fad5cc92a2fc472f1842b77af5c3590083a825ff704d747e5b9077d', 'Saja Ramzi Mahmoud Salameh', '120222222025@mutah.edu.jo', 'student', 23, 1, '2026-06-05 14:26:37'),
(23, '120222212086', 'scrypt:32768:8:1$FAQja7hsUgFOMU6W$107a1e08857e074101497165c07d41c2dbd4a1bf83c85570d5ec4696ef2a687da109423f2eb74e0c81d0f5a90f179273986d9bbbaba9c495e5ba685eeab6e4f5', 'Saja Zaid Mohammad Bashabsheh', '120222212086@mutah.edu.jo', 'student', 24, 1, '2026-06-05 14:26:37'),
(24, '120222212054', 'scrypt:32768:8:1$DM0T2DPIYkThhQoL$a26038736e32e08b4222d97e37d7ae1b5192840a3492506c6e1e1dcd00c0b9e5160ef0121354984898b56594c99148271cfad9193da22a82a6b69a63972d4b39', 'Sara Ameen Abdalhafez Maqbeh', '120222212054@mutah.edu.jo', 'student', 25, 1, '2026-06-05 14:26:37'),
(25, '120222222092', 'scrypt:32768:8:1$M7OUJXjjvEMefZiF$ae7cdf2e8aaaf7b80af863f4729f77cf31fce1aaa72551a957d56e7cf7c7db76127670eddd4cb9aa3a47fb4bf14d1a01a67b473a52b3f53051357d04887588b3', 'Sewar Yahia Jumah Sioof', '120222222092@mutah.edu.jo', 'student', 26, 1, '2026-06-05 14:26:37'),
(26, '120252212135', 'scrypt:32768:8:1$ANUNjuKjYEwuN1QX$227fa3d713eda57296fe14e045ee33370c90195b295467b5d6c27d33602207b06826e3fd5cfde1d323bfd32066be5de4981d2b5dfd9d9639ff074d15d2d17930', 'Sora Bassam Abdalghany Hjouj', '120252212135@mutah.edu.jo', 'student', 27, 1, '2026-06-05 14:26:37'),
(27, '120222222008', 'scrypt:32768:8:1$PWRXvfk7xJJzjy4T$a42f5d9e93a5c2c9e0a7b73c7ba335001c071d0cdc59c2d5efd203a6d263a54d7de1a9c539b1fe1ab898371e7f40c54daef7b178a890dcd5ca6b46250ce3e823', 'Tabark Ahmad Saleem Bdeerat', '120222222008@mutah.edu.jo', 'student', 28, 1, '2026-06-05 14:26:37'),
(28, '120232221078', 'scrypt:32768:8:1$pTOscmfGY1Ybr67n$1d464ff195e1e8d59938d96c03a2c9ea752d97dc2c149bd4f17995c866dcd70aa43f58e63349e3737a8443a9f472d9ada78c6f56cb1899184a0fe0f16db5da9b', 'Waleed Fadi Nazmi Qasem', '120232221078@mutah.edu.jo', 'student', 29, 1, '2026-06-05 14:26:37'),
(29, '120232221015', 'scrypt:32768:8:1$l0HkrjIDSmpwjnq6$5059166bc6cb641eec825eccd60f0e52b43a27b8f9617b3a5b5293512b63bd5cdc4512bfe3915a42cb6000d02230b40822d0e7709ca7ff4ce5abbc05a2caf836', 'Yaseen Yahia Salem Basiony', '120232221015@mutah.edu.jo', 'student', 30, 1, '2026-06-05 14:26:37'),
(30, '120222231083', 'scrypt:32768:8:1$3kWsoqxg3HdgKpoM$5d424b91b864cb11135c5bb97a4d2990f3d48b6b04929920cabdfc8b99297dfe36225a137537e7123df2a3abd17a6242ccad55eecf9406dc7551571b9c3a7fea', 'Yousef Jehad Musllem Rawahneh', '120222231083@mutah.edu.jo', 'student', 31, 1, '2026-06-05 14:26:37');

--
-- Indexes for dumped tables
--

--
-- Indexes for table `attendance`
--
ALTER TABLE `attendance`
  ADD PRIMARY KEY (`attendance_id`),
  ADD UNIQUE KEY `uq_attendance` (`session_id`,`student_id`),
  ADD KEY `fk_attend_student` (`student_id`),
  ADD KEY `fk_attend_override` (`override_by`);

--
-- Indexes for table `course`
--
ALTER TABLE `course`
  ADD PRIMARY KEY (`course_id`),
  ADD UNIQUE KEY `course_code` (`course_code`);

--
-- Indexes for table `excuse_request`
--
ALTER TABLE `excuse_request`
  ADD PRIMARY KEY (`excuse_id`),
  ADD KEY `student_id` (`student_id`),
  ADD KEY `section_id` (`section_id`),
  ADD KEY `session_id` (`session_id`);

--
-- Indexes for table `section`
--
ALTER TABLE `section`
  ADD PRIMARY KEY (`section_id`),
  ADD KEY `fk_section_course` (`course_id`),
  ADD KEY `fk_section_lecturer` (`lecturer_id`);

--
-- Indexes for table `section_students`
--
ALTER TABLE `section_students`
  ADD PRIMARY KEY (`enrollment_id`),
  ADD UNIQUE KEY `uq_enrollment` (`student_id`,`section_id`),
  ADD KEY `fk_enroll_section` (`section_id`);

--
-- Indexes for table `session`
--
ALTER TABLE `session`
  ADD PRIMARY KEY (`session_id`),
  ADD KEY `fk_session_section` (`section_id`),
  ADD KEY `fk_session_started_by` (`started_by`);

--
-- Indexes for table `student`
--
ALTER TABLE `student`
  ADD PRIMARY KEY (`student_id`),
  ADD UNIQUE KEY `university_id` (`university_id`),
  ADD UNIQUE KEY `email` (`email`),
  ADD UNIQUE KEY `face_label` (`face_label`),
  ADD KEY `idx_university_id` (`university_id`);

--
-- Indexes for table `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`user_id`),
  ADD UNIQUE KEY `username` (`username`),
  ADD UNIQUE KEY `email` (`email`),
  ADD KEY `idx_users_student` (`student_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `attendance`
--
ALTER TABLE `attendance`
  MODIFY `attendance_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=10;

--
-- AUTO_INCREMENT for table `course`
--
ALTER TABLE `course`
  MODIFY `course_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=5;

--
-- AUTO_INCREMENT for table `excuse_request`
--
ALTER TABLE `excuse_request`
  MODIFY `excuse_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `section`
--
ALTER TABLE `section`
  MODIFY `section_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- AUTO_INCREMENT for table `section_students`
--
ALTER TABLE `section_students`
  MODIFY `enrollment_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=111;

--
-- AUTO_INCREMENT for table `session`
--
ALTER TABLE `session`
  MODIFY `session_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=7;

--
-- AUTO_INCREMENT for table `student`
--
ALTER TABLE `student`
  MODIFY `student_id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `users`
--
ALTER TABLE `users`
  MODIFY `user_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=31;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `attendance`
--
ALTER TABLE `attendance`
  ADD CONSTRAINT `fk_attend_session` FOREIGN KEY (`session_id`) REFERENCES `session` (`session_id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_attend_student` FOREIGN KEY (`student_id`) REFERENCES `student` (`student_id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_attendance_override_by_users` FOREIGN KEY (`override_by`) REFERENCES `users` (`user_id`);

--
-- Constraints for table `excuse_request`
--
ALTER TABLE `excuse_request`
  ADD CONSTRAINT `excuse_request_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `student` (`student_id`),
  ADD CONSTRAINT `excuse_request_ibfk_2` FOREIGN KEY (`section_id`) REFERENCES `section` (`section_id`),
  ADD CONSTRAINT `excuse_request_ibfk_3` FOREIGN KEY (`session_id`) REFERENCES `session` (`session_id`);

--
-- Constraints for table `section`
--
ALTER TABLE `section`
  ADD CONSTRAINT `fk_section_course` FOREIGN KEY (`course_id`) REFERENCES `course` (`course_id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_section_lecturer` FOREIGN KEY (`lecturer_id`) REFERENCES `users` (`user_id`) ON UPDATE CASCADE;

--
-- Constraints for table `section_students`
--
ALTER TABLE `section_students`
  ADD CONSTRAINT `fk_enroll_section` FOREIGN KEY (`section_id`) REFERENCES `section` (`section_id`) ON DELETE CASCADE ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_enroll_student` FOREIGN KEY (`student_id`) REFERENCES `student` (`student_id`) ON DELETE CASCADE ON UPDATE CASCADE;

--
-- Constraints for table `session`
--
ALTER TABLE `session`
  ADD CONSTRAINT `fk_session_section` FOREIGN KEY (`section_id`) REFERENCES `section` (`section_id`) ON UPDATE CASCADE,
  ADD CONSTRAINT `fk_session_started_by_users` FOREIGN KEY (`started_by`) REFERENCES `users` (`user_id`);

--
-- Constraints for table `users`
--
ALTER TABLE `users`
  ADD CONSTRAINT `fk_users_student` FOREIGN KEY (`student_id`) REFERENCES `student` (`student_id`) ON DELETE CASCADE ON UPDATE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
